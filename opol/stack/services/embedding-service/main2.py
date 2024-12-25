from fastapi import FastAPI, HTTPException
from fastembed import TextEmbedding
from core.models import Content
import json
import logging
from redis import Redis
import asyncio
from prefect import task, flow
from core.service_mapping import ServiceConfig
from core.utils import logger
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type
import time
from prefect_ray import RayTaskRunner


app = FastAPI()
config = ServiceConfig()
token = config.HUGGINGFACE_TOKEN
model = TextEmbedding(model="jinaai/jina-embeddings-v2-base-de")

@app.get("/healthz")
async def healthcheck():
    return {"message": "NLP Service Running"}, 200


@task
def retrieve_contents_from_redis(redis_conn_raw, batch_size=50):
    batch = redis_conn_raw.lrange('contents_without_embedding_queue', 0, batch_size - 1)
    redis_conn_raw.ltrim('contents_without_embedding_queue', batch_size, -1)
    return [Content(**json.loads(content)) for content in batch]

@task
def process_content(content: Content):
    # Dynamically check if title and text_content are not None
    text_to_encode = ""
    if content.title is not None:
        text_to_encode += content.title + " "
    if content.text_content is not None:
        text_to_encode += content.text_content + " "

    # Only generate embeddings if there's text to encode
    if text_to_encode:
        embeddings = model.embed(text_to_encode)
        embeddings_list = [embedding.tolist() for embedding in embeddings]
        embeddings = embeddings_list[0]

        # Update the content with new embeddings
        content.embeddings = embeddings

        # Convert the updated content back to a dictionary
        content_dict = content.dict(exclude_unset=True)

        logger.info(f"Generated embeddings for content: {content.url}, Embeddings Length: {len(embeddings)}")
        return content_dict
    else:
        logger.warning(f"No text available to generate embeddings for content: {content.url}")
        return None

@task
def write_contents_to_redis(redis_conn_processed, contents_with_embeddings):
    serialized_contents = [json.dumps(content) for content in contents_with_embeddings]
    if serialized_contents:  # Check if the list is not empty
        redis_conn_processed.lpush('contents_with_embeddings', *serialized_contents)
        logger.info(f"Wrote {len(contents_with_embeddings)} contents with embeddings to Redis")
    else:
        logger.info("No contents to write to Redis")
        
@flow(task_runner=RayTaskRunner())
def generate_embeddings_flow(batch_size: int):
    logger.info("Starting embeddings generation process")
    redis_conn_raw = Redis(host='redis', port=6379, db=5, decode_responses=True)
    redis_conn_processed = Redis(host='redis', port=6379, db=6, decode_responses=True)

    try:
        raw_contents = retrieve_contents_from_redis(redis_conn_raw, batch_size)
        _contents_with_embeddings = [process_content(content) for content in raw_contents]
        write_contents_to_redis(redis_conn_processed, _contents_with_embeddings)
    finally:
        redis_conn_raw.close()
        redis_conn_processed.close()
        time.sleep(1)

    logger.info("Embeddings generation process completed")

    
@app.post("/generate_embeddings")
def generate_embeddings(batch_size: int = 100):
    logger.debug("GENERATING EMBEDDINGS")
    generate_embeddings_flow(batch_size)
    return {"message": "Embeddings generated successfully"}

@app.get("/generate_query_embeddings")
def generate_query_embedding(query: str):
    try:
        embeddings = model.encode(query).tolist()
        logger.info(f"Generated embeddings for query: {query}, Embeddings Length: {len(embeddings)}")
        return {"embeddings": embeddings}
    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
