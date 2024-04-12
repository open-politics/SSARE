from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from typing import List
from redis.asyncio import Redis
from core.models import ArticleBase
import json
from pydantic import ValidationError
import logging
from core.utils import load_config
from prefect import flow, task, get_run_logger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
This Service runs on port 0420 and is responsible for generating embeddings for articles.
"""

config = load_config()['nlp']

app = FastAPI()

token = config['HUGGINGFACE_TOKEN']

model = SentenceTransformer("jinaai/jina-embeddings-v2-base-en", use_auth_token=token)


@app.get("/healthz")
async def healthcheck():
    return {"message": "NLP Service Running"}, 200


@task
async def retrieve_articles_from_redis(redis_conn_raw):
    logger = get_run_logger()
    raw_articles_json = await redis_conn_raw.lrange('articles_without_embedding_queue', 0, -1)
    logger.info(f"Retrieved {len(raw_articles_json)} articles from Redis")
    return raw_articles_json


@task
async def process_article(raw_article_json, model):
    logger = get_run_logger()
    raw_article = json.loads(raw_article_json.decode('utf-8'))
    article = ArticleBase(**raw_article)

    embeddings = model.encode(article.headline + " ".join(article.paragraphs)).tolist()

    article_with_embeddings = {
        "headline": article.headline,
        "paragraphs": article.paragraphs,
        "embeddings": embeddings,
        "embeddings_created": 1,
        "url": article.url,
        "source": article.source,
        "stored_in_qdrant": 0
    }

    logger.info(f"Generated embeddings for article: {article.url}, Embeddings Length: {len(embeddings)}")
    logger.info(f"Article: {article.url}")
    logger.info(f"Headline: {article.headline}")
    logger.info(f"First 30 paragraphs: {article.paragraphs[:30]}")
    logger.info(f"First 3 embeddings: {embeddings[:3]}")

    return article_with_embeddings


@task
async def write_article_to_redis(redis_conn_processed, article_with_embeddings):
    logger = get_run_logger()
    await redis_conn_processed.lpush('articles_with_embeddings', json.dumps(article_with_embeddings))
    logger.info(f"Article with embeddings written to Redis: {article_with_embeddings['url']}")


@flow
async def generate_embeddings_flow():
    logger = get_run_logger()
    try:
        redis_conn_raw = await Redis(host='redis', port=6379, db=5)
        redis_conn_processed = await Redis(host='redis', port=6379, db=6)

        raw_articles_json = await retrieve_articles_from_redis(redis_conn_raw)
        logger.info("Starting embeddings generation process")

        for raw_article_json in raw_articles_json:
            try:
                article_with_embeddings = await process_article(raw_article_json, model)
                await write_article_to_redis(redis_conn_processed, article_with_embeddings)
            except Exception as e:
                logger.error(f"Error processing article: {e}")

        logger.info("Embeddings generation process completed")
        return {"message": "Embeddings generated"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/generate_embeddings")
async def generate_embeddings():
    """
    This function generates embeddings for articles that do not have embeddings.
    It is triggered by an API call from the orchestration container.
    It reads from redis queue 5 - channel articles_without_embedding_queue.
    It writes to redis queue 6 - channel articles_with_embeddings.
    """
    return await generate_embeddings_flow()


@app.get("/generate_query_embeddings")
async def generate_query_embedding(query: str):
    """
    This function generates embeddings for a query.
    It is triggered by an API call from the orchestration container.
    """
    try:
        embeddings = model.encode(query).tolist()  # Ensure embeddings are JSON serializable
        logger.info(f"Generated embeddings for query: {query}, Embedding Length: {len(embeddings)}")
        first_10_embeddings = embeddings[:10]
        logger.info(f"First 10 embeddings: {first_10_embeddings}")

        # Include embeddings in the response
        return {"message": "Embeddings generated", "embeddings": embeddings}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
