from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from typing import List
from redis.asyncio import Redis
from core.models import ArticleBase
from core.utils import load_config
import httpx
import requests
import json
from core.models import ArticleBase
"""
This Service runs on port 0420 and is responsible for generating embeddings for articles.
"""

app = FastAPI()

model = SentenceTransformer('jinaai/jina-embeddings-v2-base-en')

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
        raw_articles = await redis_conn_raw.lrange('articles_without_embedding_queue', 0, -1)
        raw_articles = [article.decode('utf-8') for article in raw_articles]

        redis_conn_processed = await Redis(host='redis', port=6379, db=6)



        for raw_article in raw_articles:
            article = ArticleBase(**json.loads(raw_article))
            embedding = model.encode(article.headline + " ".join(article.paragraphs)).tolist()

            article_with_embedding = article.model_dump()
            article_with_embedding["embeddings"] = embedding

            await redis_conn_processed.lpush('articles_with_embeddings', json.dumps(article_with_embedding))




        return {"message": "Embeddings generated and pushed to queue."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


