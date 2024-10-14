import os
import json
import logging
from typing import List
from redis import Redis
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pydantic import BaseModel, Field, validator
from prefect import flow, task
import time
from uuid import UUID

from openai import OpenAI
import instructor

from core.models import Content, ContentClassification
from core.utils import UUIDEncoder, logger
from core.service_mapping import ServiceConfig

app = FastAPI()
config = ServiceConfig()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

# Configure OpenAI or local LLM client
if os.getenv("LOCAL_LLM") == "True":
    client = instructor.from_openai(OpenAI(base_url="http://litellm:4000", api_key="sk-1234"))
else:
    client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

# Extraction Data Model
class ContentClassificationModel(BaseModel):
    category: str
    secondary_categories: List[str]
    keywords: List[str]
    geopolitical_relevance: int
    legislative_influence_score: int
    international_relevance_score: int
    democratic_process_implications_score: int
    general_interest_score: int
    spam_score: int
    clickbait_score: int
    fake_news_score: int
    satire_score: int
    event_type: str

    @validator('*', pre=True, each_item=True)
    def parse_int_fields(cls, v, field):
        int_fields = [
            'geopolitical_relevance', 'legislative_influence_score',
            'international_relevance_score', 'democratic_process_implications_score',
            'general_interest_score', 'spam_score', 'clickbait_score',
            'fake_news_score', 'satire_score'
        ]
        if field.name in int_fields:
            if not isinstance(v, int):
                raise ValueError(f"Value {v} is not an integer")
            if not (0 <= v <= 10):
                raise ValueError(f"Value {v} is out of range (0-10)")
        return v

    @validator('secondary_categories', 'keywords', pre=True)
    def parse_list_fields(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [item.strip() for item in v.strip('[]').split(',')]
        return v

# Functions for LLM tasks
@task(retries=3)
def classify_content(content: Content) -> ContentClassificationModel:
    """Classify the content using LLM."""
    text_to_analyze = content.text_content or ""
    if content.media_details and content.media_details.transcribed_text:
        text_to_analyze += content.media_details.transcribed_text

    return client.chat.completions.create(
        model="gpt-4" if os.getenv("LOCAL_LLM") == "False" else "local-llm-model",
        response_model=ContentClassificationModel,
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant that analyzes content and provides tags and metrics for an open-source political intelligence service."
            },
            {
                "role": "user",
                "content": f"Analyze this content and provide tags and metrics:\n\nTitle: {content.title}\n\nContent: {text_to_analyze[:500]}, be very critical."
            },
        ],
    )

@task
def retrieve_contents_from_redis(batch_size: int = 50) -> List[Content]:
    """Retrieve contents from Redis queue."""
    redis_conn = Redis(host='redis', port=6379, db=4)
    _contents = redis_conn.lrange('contents_without_classification_queue', 0, batch_size - 1)
    redis_conn.ltrim('contents_without_classification_queue', batch_size, -1)

    if not _contents:
        logger.warning("No contents retrieved from Redis.")
        return []

    contents = []
    for content_data in _contents:
        try:
            content_dict = json.loads(content_data)
            content = Content(**content_dict)
            contents.append(content)
        except Exception as e:
            logger.error(f"Invalid content: {content_data}")
            logger.error(f"Error: {e}")

    return contents

@flow
def process_contents(batch_size: int = 50):
    """Process a batch of contents: retrieve, classify, and serialize them."""
    contents = retrieve_contents_from_redis(batch_size=batch_size)

    if not contents:
        logger.warning("No contents to process.")
        return []

    logger.info(f"Processing: {len(contents)} contents")

    processed_contents = []
    for content in contents:
        try:
            classification = classify_content(content)

            # Combine content and classification data
            content_dict = content.dict()
            content_dict['classification'] = classification.dict()

            processed_contents.append(json.dumps(content_dict, cls=UUIDEncoder))
            logger.info(f"Classified content: {content.url}")

            if os.getenv("LOCAL_LLM") == "True":
                time.sleep(2)
        except Exception as e:
            logger.error(f"Error processing content: {content.url}")
            logger.error(f"Error: {e}")

    if processed_contents:
        write_contents_to_redis(processed_contents)
    return processed_contents

def write_contents_to_redis(serialized_contents):
    """Write serialized contents to Redis."""
    if not serialized_contents:
        logger.info("No contents to write to Redis")
        return

    redis_conn_processed = Redis(host='redis', port=6379, db=4)
    redis_conn_processed.lpush('contents_with_classification_queue', *serialized_contents)
    logger.info(f"Wrote {len(serialized_contents)} contents with classification to Redis")

@app.post("/classify_contents")
def classify_contents_endpoint(batch_size: int = 50):
    logger.debug("Processing contents")
    processed_contents = process_contents(batch_size)

    if not processed_contents:
        return {"message": "No contents processed."}

    return {
        "message": "Contents processed successfully",
        "processed_count": len(processed_contents),
    }

# Health endpoint
@app.get("/healthz")
def healthz():
    return {"status": "OK"}
