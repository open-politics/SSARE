from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from typing import List
from redis.asyncio import Redis
from core.models import ArticleBase
import json
from pydantic import ValidationError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
This Service runs on port 0420 and is responsible for generating embeddings for articles.
"""

app = FastAPI()

model = SentenceTransformer("all-MiniLM-L6-v2")

@app.post("/generate_embeddings")
async def generate_embeddings():
    """
    This function generates embeddings for articles that do not have embeddings.
    It is triggered by an API call from the orchestration container. 
    It reads from redis queue 5 - channel articles_without_embedding_queue.
    It writes to redis queue 6 - channel articles_with_embeddings.
    """
    try:
        redis_conn_raw = await Redis(host='redis', port=6379, db=5)
        redis_conn_processed = await Redis(host='redis', port=6379, db=6)

        # Retrieve articles from Redis Queue 5
        raw_articles_json = await redis_conn_raw.lrange('articles_without_embedding_queue', 0, -1)

        for raw_article_json in raw_articles_json:
            try:
                # Decode and load the article
                raw_article = json.loads(raw_article_json.decode('utf-8'))
                article = ArticleBase(**raw_article)

                # Generate embeddings
                embedding = model.encode(article.headline + " ".join(article.paragraphs)).tolist()
                article_with_embedding = article.model_dump()
                article_with_embedding["embeddings"] = embedding

                # Push to Redis Queue 6
                await redis_conn_processed.lpush('articles_with_embeddings', json.dumps(article_with_embedding))
            except (json.JSONDecodeError, ValidationError) as e:
                logger.error(f"Error processing article: {e}")

        return {"message": "Embeddings generated"}
    except Exception as e:
        logger.error(f"Error in generating embeddings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

