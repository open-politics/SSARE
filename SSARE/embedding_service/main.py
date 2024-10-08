from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer
from core.models import Article, Articles
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
model = SentenceTransformer("jinaai/jina-embeddings-v2-base-en", 
                            use_auth_token=token,
                            trust_remote_code=True)

@app.get("/healthz")
async def healthcheck():
    return {"message": "NLP Service Running"}, 200


@task
def retrieve_articles_from_redis(redis_conn_raw, batch_size=50):
    batch = redis_conn_raw.lrange('articles_without_embedding_queue', 0, batch_size - 1)
    redis_conn_raw.ltrim('articles_without_embedding_queue', batch_size, -1)
    return [Article(**json.loads(article)) for article in batch]

@task
def process_article(article: Article):
    # Dynamically check if headline and paragraphs are not None
    text_to_encode = ""
    if article.headline is not None:
        text_to_encode += article.headline + " "
    if article.paragraphs is not None:
        text_to_encode += article.paragraphs + " "
    
    # Only generate embeddings if there's text to encode
    if text_to_encode:
        embeddings = model.encode(text_to_encode).tolist()
        
        # Update the article with new embeddings
        article.embeddings = embeddings
        
        # Convert the updated article back to a dictionary
        article_dict = article.dict(exclude_unset=True)
        
        logger.info(f"Generated embeddings for article: {article.url}, Embeddings Length: {len(embeddings)}")
        return article_dict
    else:
        logger.warning(f"No text available to generate embeddings for article: {article.url}")
        return None

@task
def write_articles_to_redis(redis_conn_processed, articles_with_embeddings):
    serialized_articles = [json.dumps(article) for article in articles_with_embeddings]
    if serialized_articles:  # Check if the list is not empty
        redis_conn_processed.lpush('articles_with_embeddings', *serialized_articles)
        logger.info(f"Wrote {len(articles_with_embeddings)} articles with embeddings to Redis")
    else:
        logger.info("No articles to write to Redis")
        
@flow(task_runner=RayTaskRunner())
def generate_embeddings_flow(batch_size: int):
    logger.info("Starting embeddings generation process")
    redis_conn_raw = Redis(host='redis', port=6379, db=5, decode_responses=True)
    redis_conn_processed = Redis(host='redis', port=6379, db=6, decode_responses=True)

    try:
        raw_articles = retrieve_articles_from_redis(redis_conn_raw, batch_size)
        _articles_with_embeddings = [process_article(article) for article in raw_articles]
        write_articles_to_redis(redis_conn_processed, _articles_with_embeddings)
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