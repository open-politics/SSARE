from fastapi import FastAPI, HTTPException
import httpx
from qdrant_client import QdrantClient
import json
from redis.asyncio import Redis
from sqlalchemy import update
from core.models import ProcessedArticleModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from core.models import ArticleBase

"""
This Service runs on port 6969 and is responsible qdrant related event-handling.
It is responsible for:
1. Creating embeddings jobs
2. Storing embeddings in Qdrant
3. Updating the flags in PostgreSQL for articles that have embeddings
4. [TODO] Querying Qdrant
"""


app = FastAPI()

qdrant_client = QdrantClient(host='qdrant_service', port=6333)
collection_name = 'articles'

@app.get("/healthcheck")
async def healthcheck():
    return {"message": "OK"}

# Add exception handler for RequestValidationError
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.errors(), "body": exc.body},
    )


# get articles from postgres and create embeddings
@app.post("/create_embedding_jobs")
async def create_embeddings_jobs():
    """
    This function is triggered by an api. It reads from postgres /articles where embeddings_created = 0.
    It writes to redis queue 5 - channel articles_without_embedding_queue.
    It doesn't trigger the generate_embeddings function in nlp_service. That is done by the scheduler.
    """
    try:
        async with httpx.AsyncClient() as client:
            articles_without_embeddings = await client.get("http://postgres_service:5432/articles")
            articles_without_embeddings = articles_without_embeddings.json()

        redis_conn_unprocessed_articles = Redis(host='redis', port=6379, db=5)
        for article in articles_without_embeddings:
            await redis_conn_unprocessed_articles.lpush('articles_without_embedding_queue', json.dumps(article))

        return {"message": "Embedding jobs created."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

# get articles from postgres and create embeddings
@app.post("/store_embeddings")
async def store_embeddings():
    """
    This function is triggered by an api. It reads from redis queue 6 - channel articles_with_embeddings.
    It stores the embeddings in Qdrant.

    """
    try:
        redis_conn = await Redis(host='redis', port=6379, db=6)
        urls_to_update = []
        articles_with_embedding_json = await redis_conn.rpop('articles_with_embeddings')

        while True:
            article_with_embedding = json.loads(articles_with_embedding_json)
            validated_article = ArticleBase(**article_with_embedding)

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
            urls_to_update.append(validated_article.url)
            
            async with httpx.AsyncClient() as client:
                await client.post("http://postgres_service:5432/update_qdrant_flags", json={"urls": urls_to_update})

        return {"message": "Embeddings processed and stored in Qdrant."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))