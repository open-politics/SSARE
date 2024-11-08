import os
import json
import logging
from typing import List
from redis import Redis
from fastapi import FastAPI
from contextlib import asynccontextmanager
from openai import OpenAI
import instructor
from models import ContentEvaluation
from core.utils import UUIDEncoder, logger
from core.models import Content
from core.service_mapping import ServiceConfig
from pydantic import BaseModel, Field
from pydantic import validator, field_validator
from prefect import flow, task
from prefect.logging import get_run_logger
import time
from uuid import UUID
from pydantic import BaseModel, field_validator
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from classx import create_dynamic_classification_model, build_system_prompt
from core.adb import get_session
from sqlalchemy.orm import selectinload
from fastapi import FastAPI, HTTPException, Depends, Query, APIRouter
from core.adb import get_session
from core.models import ClassificationDimension, ClassificationType
from prefect.logging import get_run_logger




app = FastAPI()
config = ServiceConfig()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

# Configure LiteLLM
my_proxy_api_key = "sk-1234"
my_proxy_base_url = "http://litellm:4000"

client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))


from models import ContentEvaluation

# Functions for LLM tasks
@task(retries=1)
def classify_content(content: Content) -> ContentEvaluation:
    """Classify the content using LLM and evaluate it."""
    logger = get_run_logger()
    logger.info(f"Starting classification for content: {content.title}")
    
    response = client.chat.completions.create(
        model="gpt-4o-2024-08-06",
        response_model=ContentEvaluation,
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant that analyzes articles and provides comprehensive evaluations across various dimensions such as rhetoric, global impact, political impact, economic impact, and event type."
            },
            {
                "role": "user",
                "content": f"Evaluate this article and provide a comprehensive analysis:\n\nHeadline: {content.title}\n\nContent: {content.text_content if os.getenv('LOCAL_LLM') == 'False' else content.text_content[:320]}, be very critical.",
            },
        ],
    )
    logger.info("Classification completed successfully")
    return response

@task
def retrieve_contents_from_redis(batch_size: int = 10) -> List[Content]:
    """Retrieve contents from Redis queue."""
    logger = get_run_logger()
    logger.info(f"Attempting to retrieve {batch_size} contents from Redis")
    
    redis_conn = Redis(host='redis', port=6379, db=4)
    # temp override: batch size = 2
    batch_size = 2
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

    logger.info(f"Successfully retrieved {len(contents)} contents")
    return contents

@flow(log_prints=True)
def process_and_print_contents(batch_size: int = 10):
    """Process a batch of contents: retrieve, classify, and print them."""
    logger = get_run_logger()
    contents = retrieve_contents_from_redis(batch_size=batch_size)

    if not contents:
        logger.warning("No contents to process.")
        return []

    logger.info(f"Processing: {len(contents)} contents")

    evaluations = []
    for content in contents:
        try:
            evaluation = classify_content(content)
            logger.info(f"Evaluation completed for content: {content.title}")
            logger.debug(json.dumps(evaluation.dict(), indent=2))
            _return_object = {
                "title": content.title,
                "text_content": content.text_content,
                "evaluations": evaluation.dict()
            }
            evaluations.append(_return_object)
            if os.getenv("LOCAL_LLM") == "True":
                time.sleep(2)
        except Exception as e:
            logger.error(f"Error processing content: {content}")
            logger.error(f"Error: {e}")
    
    logger.info(f"Successfully processed {len(evaluations)} contents")
    return evaluations

@app.post("/test_classify_contents")
def test_classify_contents_endpoint(batch_size: int = 10):
    logger.debug("Testing classification of contents")
    evaluations = process_and_print_contents(batch_size)
    return {"evaluations": evaluations}

# Health endpoint
@app.get("/healthz")
def healthz():
    return {"status": "OK"}

from pydantic import BaseModel
from typing import Optional, List, Union

# Input model for dynamic dimension
class DimensionInput(BaseModel):
    name: str
    type: ClassificationType
    description: str

# Input model for the classification request
class ClassificationRequest(BaseModel):
    content: dict  # The article content
    dimensions: Optional[List[DimensionInput]] = None  # Optional dimensions to create/use
    dimension_names: Optional[List[str]] = None  # Optional list of existing dimension names to use


@app.post("/test_dynamic_classification")
async def test_dynamic_classification_endpoint(
    request: ClassificationRequest,
    session: AsyncSession = Depends(get_session)
):
    """Process dynamic classification request."""
    # setup prefect logger

    try:
        logger.debug(f"Processing classification request for content ID: {request.content.get('id')}")
        content = Content(**request.content)
        dimensions = []
        
        # Instead of creating dimensions, just fetch existing ones
        if request.dimensions:
            for dim_input in request.dimensions:
                result = await session.execute(
                    select(ClassificationDimension)
                    .where(ClassificationDimension.name == dim_input.name)
                )
                dimension = result.scalar_one_or_none()
                if dimension:
                    dimensions.append(dimension)
                    
        elif request.dimension_names:
            result = await session.execute(
                select(ClassificationDimension)
                .where(ClassificationDimension.name.in_(request.dimension_names))
            )
            dimensions = result.scalars().all()
            
        else:
            result = await session.execute(select(ClassificationDimension))
            dimensions = result.scalars().all()

        if not dimensions:
            raise HTTPException(
                status_code=400,
                detail="No valid dimensions found for classification"
            )

        # Create dynamic pydantic model and continue with classification
        DynamicClassificationModel = create_dynamic_classification_model(dimensions)
        system_prompt = build_system_prompt(dimensions)
        
        classification = client.chat.completions.create(
            model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4",
            response_model=DynamicClassificationModel,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this article and provide the classifications.\n\nHeadline: {content.title}\n\nContent: {content.text_content[:320]}"},
            ],
        )

        return {
            "classifications": classification.dict(),
            "dimensions_used": [{"name": d.name, "type": d.type, "description": d.description} for d in dimensions]
        }
        
    except Exception as e:
        logger.error(f"Error in classification service: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



class ContentIsRelevant(BaseModel):
    is_relevant: bool
    reason: str

def is_content_relevant(content: Content) -> ContentIsRelevant:
    return ContentIsRelevant(is_relevant=True, reason="It's a test")


def analyse_texts_mock(texts):
    for text in texts:
        is_relevant = is_content_relevant(text)

        

