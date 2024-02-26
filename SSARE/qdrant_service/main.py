from fastapi import FastAPI, HTTPException
import httpx
from qdrant_client import QdrantClient
import json
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
from core.models import ArticleBase
import logging
from typing import List

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
This Service runs on port 6969 and is responsible qdrant related event-handling.
It is responsible for:
1. Creating embeddings jobs
2. Storing embeddings in Qdrant
3. Updating the flags in PostgreSQL for articles that have embeddings
4. [TODO] Querying Qdrant
"""


app = FastAPI()

qdrant_client = QdrantClient(host='localhost', port=6333)
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
    logger.info("Trying to create embedding jobs.")
    try:
        async with httpx.AsyncClient() as client:
            articles_without_embeddings = await client.get("http://postgres_service:5434/articles?embeddings_created=0")
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
        logger.info("Trying to store embeddings in Qdrant.")
        redis_conn = await Redis(host='redis', port=6379, db=6)
        logger.info("Connected to Redis.")
        urls_to_update = []
        articles_with_embedding_json = await redis_conn.rpop('articles_with_embeddings')
        logger.info(articles_with_embedding_json)
        logger.info("Popped from Redis.")

        while True:
            if articles_with_embedding_json is None:
                logger.info("No more articles to process.")
                break
            article_with_embedding = json.loads(articles_with_embedding_json)
            validated_article = ArticleBase(**article_with_embedding)

            payload = {
                "headline": article_with_embedding["headline"],
                "text": " ".join(article_with_embedding["paragraphs"]),  # Combine paragraphs into a single text
                "source": article_with_embedding["source"],
                "url": article_with_embedding["url"],
            }

            from qdrant_client.http.models import Distance, VectorParams
            qdrant_client.create_collection(
                collection_name="Articles",
                vector_size=VectorParams(size=768, distance= Distance.DOT),
            )

            operation_info = qdrant_client.upsert(
                collection_name="Articles",
                points=[{
                    "id": article_with_embedding["url"],  # Use URL as unique identifier
                    "vector": article_with_embedding["embeddings"],
                    "payload": payload
                }]
            )
            logger.info(f"Upsert Operation: {validated_article.url}")
            urls_to_update.append(validated_article.url)
            
            async with httpx.AsyncClient() as client:
                await client.post("http://postgres_service:5434/update_qdrant_flags", json={"urls": urls_to_update})
                logger.info("Updated qdrant flags for articles.")

        return {"message": "Embeddings processed and stored in Qdrant."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

@app.post("/search")
async def search(embeddings: List[float]):
    try:
        search_response = qdrant_client.search(
           collection_name="Articles",
            query_vector=embeddings,
            limit=10  # Number of top similar results to return
        )
        return search_response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
