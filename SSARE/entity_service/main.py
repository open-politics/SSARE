import json
import logging
from typing import List, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from redis import Redis
from core.service_mapping import ServiceConfig
from core.utils import logger, UUIDEncoder
from core.models import Content, Entity 
from prefect import task, flow
import uuid
from gliner import GLiNER  
from prefect_ray.task_runners import RayTaskRunner
app = FastAPI()
config = ServiceConfig()

# Load the GLiNER model
ner_tagger = GLiNER.from_pretrained("EmergentMethods/gliner_medium_news-v2.1")

# Define the labels for GLiNER
labels = ["person", "location", "topic",  "date", "event", "state", "number", "organization", "region", "alliance"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

@task
def retrieve_contents_from_redis(redis_conn, batch_size=50) -> List[Content]:
    batch = redis_conn.lrange('contents_without_entities_queue', 0, batch_size - 1)
    redis_conn.ltrim('contents_without_entities_queue', batch_size, -1)
    return [Content(**json.loads(content)) for content in batch]

def split_text_into_chunks(text: str, max_length: int, overlap: int = 50) -> List[str]:
    words = text.split()
    chunks = []
    start = 0

    while start < len(words):
        end = min(start + max_length, len(words))
        chunk = ' '.join(words[start:end])
        chunks.append(chunk)
        start += max_length - overlap  # Move the window forward with overlap

    return chunks

@task
def predict_ner_tags(text: str) -> List[Tuple[str, str]]:
    # Split text into manageable chunks
    max_length = 50  # Adjusting this based on the model's max token length
    text_chunks = split_text_into_chunks(text, max_length)
    
    entities = []
    for chunk in text_chunks:
        # Using GLiNER to predict entities for each chunk
        chunk_entities = ner_tagger.predict_entities(chunk, labels)
        entities.extend([(entity["text"], entity["label"]) for entity in chunk_entities])
    
    return entities

@task
def process_content(content: Content) -> Tuple[Content, List[Tuple[str, str]]]:
    text = ""
    if content.title:
        text += content.title + " "
    if content.text_content:
        text += content.text_content
    entities = predict_ner_tags(text.strip())
    return (content, entities)

@task
def push_contents_with_entities(redis_conn, contents_with_entities: List[Tuple[Content, List[Tuple[str, str]]]]):
    try:
        for content, entities in contents_with_entities:
            entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
            content_dict = content.dict()
            content_dict['entities'] = entities_data
            redis_conn.lpush('contents_with_entities_queue', json.dumps(content_dict, cls=UUIDEncoder))
            logger.info(f"Content with entities pushed to queue: {content.url}")
    except Exception as e:
        logger.error(f"Error pushing contents with entities to queue: {str(e)}")

@flow(task_runner=RayTaskRunner())
def extract_entities_flow(batch_size: int = 50):
    logger.info("Starting entity extraction process")
    redis_conn = Redis(host='redis', port=6379, db=2, decode_responses=True)

    try:
        contents = retrieve_contents_from_redis(redis_conn, batch_size)
        if contents:
            contents_with_entities = [process_content(content) for content in contents]
            push_contents_with_entities(redis_conn, contents_with_entities)
            logger.info(f"Entities extracted for {len(contents)} contents.")
        else:
            logger.info("No contents found in the queue.")
    finally:
        redis_conn.close()

    return {"message": "Entity extraction completed"}

@app.post("/extract_entities")
def generate_entities(batch_size: int = 50):
    logger.info("Generating entities")
    return extract_entities_flow(batch_size)

@app.get("/healthz")
def healthz():
    return {"message": "ok"}

@app.get("/fetch_entities")
def fetch_entities(text: str):
    try:
        entities = predict_ner_tags(text)
        entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
        return {"entities": entities_data}
    except Exception as e:
        logger.error(f"Error fetching entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))
