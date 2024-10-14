from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer
from core.models import Content
import json
import logging
from redis import Redis
from prefect import task, flow
from core.service_mapping import ServiceConfig
from core.utils import logger
import time

app = FastAPI()
config = ServiceConfig()
token = config.HUGGINGFACE_TOKEN
model = SentenceTransformer("jinaai/jina-embeddings-v2-base-en", 
                            use_auth_token=token,
                            trust_remote_code=True)

@app.get("/healthz")
async def healthcheck():
    return {"message": "Embedding Service Running"}, 200

@task
def retrieve_contents_from_redis(redis_conn_raw, batch_size=50):
    batch = redis_conn_raw.lrange('contents_without_embedding_queue', 0, batch_size - 1)
    redis_conn_raw.ltrim('contents_without_embedding_queue', batch_size, -1)
    return [Content(**json.loads(content)) for content in batch]

@task
def process_content(content: Content):
    # Combine text content and transcribed text if available
    text_to_encode = content.text_content or ""
    if content.media_details and content.media_details.transcribed_text:
        text_to_encode += " " + content.media_details.transcribed_text

    if text_to_encode.strip():
        embeddings = model.encode(text_to_encode.strip()).tolist()
        content.embeddings = embeddings
        content_dict = content.dict(exclude_unset=True)
        logger.info(f"Generated embeddings for content: {content.url}")
        return content_dict
    else:
        logger.warning(f"No text available to generate embeddings for content: {content.url}")
        return None

@task
def write_contents_to_redis(redis_conn_processed, contents_with_embeddings):
    serialized_contents = [json.dumps(content) for content in contents_with_embeddings if content]
    if serialized_contents:
        redis_conn_processed.lpush('contents_with_embeddings', *serialized_contents)
        logger.info(f"Wrote {len(serialized_contents)} contents with embeddings to Redis")
    else:
        logger.info("No contents to write to Redis")

@flow
def generate_embeddings_flow(batch_size: int):
    logger.info("Starting embeddings generation process")
    redis_conn_raw = Redis(host='redis', port=6379, db=5, decode_responses=True)
    redis_conn_processed = Redis(host='redis', port=6379, db=6, decode_responses=True)

    try:
        raw_contents = retrieve_contents_from_redis(redis_conn_raw, batch_size)
        contents_with_embeddings = [process_content(content) for content in raw_contents]
        write_contents_to_redis(redis_conn_processed, contents_with_embeddings)
    finally:
        redis_conn_raw.close()
        redis_conn_processed.close()
        time.sleep(1)

    logger.info("Embeddings generation process completed")

@app.post("/generate_embeddings")
def generate_embeddings(batch_size: int = 100):
    logger.debug("Generating embeddings")
    generate_embeddings_flow(batch_size)
    return {"message": "Embeddings generated successfully"}

@app.get("/generate_query_embeddings")
def generate_query_embedding(query: str):
    try:
        embeddings = model.encode(query).tolist()
        logger.info(f"Generated embeddings for query: {query}")
        return {"embeddings": embeddings}
    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/healthz")
def healthz():
    return {"message": "ok"}