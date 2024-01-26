from fastapi import FastAPI, HTTPException
import httpx
from qdrant_client import QdrantClient
from redis import Redis
import json
from sqlalchemy import update
from core.models import ProcessedArticleModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


app = FastAPI()

qdrant_client = QdrantClient(host='qdrant_service', port=6333)
collection_name = 'articles'

@app.get("/healthcheck")
async def healthcheck():
    return {"message": "OK"}


# get articles from postgres and create embeddings
@app.post("/create_embedding_jobs")
async def create_embeddings_jobs():
    try:
        async with httpx.AsyncClient() as client:
            articles_without_embeddings = await client.get("http://postgres_service:5432/articles")
            articles_without_embeddings = articles_without_embeddings.json()

        redis_conn_unprocessed_articles = await Redis(host='redis', port=6379, db=5)
        for article in articles_without_embeddings:
            await redis_conn_unprocessed_articles.lpush('articles_without_embedding_queue', json.dumps(article))

        return {"message": "Embedding jobs created."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

# get articles from postgres and create embeddings
@app.post("/store_embeddings")
async def store_embeddings():
    try:
        redis_conn = await Redis(host='redis', port=6379, db=6)
        urls_to_update = []
        while True:
            article_with_embedding_json = await redis_conn.rpop('articles_with_embeddings')
            if article_with_embedding_json is None:
                break  # Exit if the queue is empty


            article_with_embedding = json.loads(article_with_embedding_json)
            payload = {
                "headline": article_with_embedding["headline"],
                "text": " ".join(article_with_embedding["paragraphs"]),  # Combine paragraphs into a single text
                "source": article_with_embedding["source"],
                "url": article_with_embedding["url"],
            }

            qdrant_client.upsert(
                collection_name=collection_name,
                points=[{
                    "id": article_with_embedding["url"],  # Use URL as unique identifier
                    "vector": article_with_embedding["embeddings"],
                    "payload": payload
                }]
            )
            urls_to_update.append(article_with_embedding["url"])
            
            async with httpx.AsyncClient() as client:
                await client.post("http://postgres_service:5432/update_qdrant_flags", json={"urls": urls_to_update})

        return {"message": "Embeddings processed and stored in Qdrant."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))