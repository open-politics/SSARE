from fastapi import FastAPI, HTTPException
import httpx
from qdrant_client import QdrantClient
from qdrant_client.http.models import VectorParams, Distance, PointStruct
import json
import uuid
from redis.asyncio import Redis
from sqlalchemy import update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse
import logging
from pydantic import BaseModel
from typing import List, Optional

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

"""
This Service runs on port 6969 and is responsible qdrant related event-handling.
It is responsible for:
1. Creating embeddings jobs
2. Storing embeddings in Qdrant
3. Updating the flags in PostgreSQL for articles that have embeddings
"""

app = FastAPI()

# As a reminder of the data structure
class ArticleModel(BaseModel):
    url: str
    headline: str
    paragraphs: str  # JSON string
    source: Optional[str]
    embeddings: Optional[List[float]]
    embeddings_created: int = 1
    stored_in_qdrant: int = 0

# Configs
qdrant_client = QdrantClient(host='qdrant_storage', port=6333)
vectors_config = VectorParams(size=768, distance=Distance.COSINE)
collection_name = 'articles'

# Early defined function as a fallback if no new qdrant collection needs be created
def recreate_collection(qdrant_client, collection_name, vectors_config):
    """
    This function recreates the collection in Qdrant.
    """
    qdrant_client.delete_collection(collection_name)
    create_collection_info = qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=vectors_config,
    )
    logger.info(f"Collection recreated: {create_collection_info}")
    return create_collection_info

# 1. Task of this service: Try to create the collection if it does not exist, continue if it does
try:
    create_collection_info = qdrant_client.create_collection(
                    collection_name="articles",
                    vectors_config=vectors_config,
                )
    logger.info(f"Collection created: {create_collection_info}")
except Exception as e:
    logger.info(f"Collection already exists: {e}")
    recreated_collection_result = recreate_collection(qdrant_client, collection_name, vectors_config)
    logger.info(f"Recreating collection: {recreated_collection_result}")

# Safety Blah
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"detail": exc.errors(), "body": exc.body},
    )

# Health endpoint
@app.get("/health")
async def healthcheck():
    return {"message": "OK"}, 200

# Health endpoint for Helm
@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}, 200


# 2. INSERT FUNCTION: is async triggered, pulls jobs from pipeline and creates qdrant point structs
# Can be highly optimized (wink wink)
@app.post("/store_embeddings")
async def store_embeddings():
    logger.info("Starting to store embeddings in Qdrant.")
    try:
        redis_conn = await Redis(host='redis', port=6379, db=6)
        logger.info("Connected to Redis.")
        urls_to_update = []
        points = []

        while True:
            article_json = await redis_conn.rpop('articles_with_embeddings')
            if article_json is None:
                logger.info("No more articles to process.")
                break

            try:
                article = json.loads(article_json)
                if 'embeddings' not in article or not article['embeddings']:
                    logger.warning(f"Skipping article with missing or empty embeddings: {article.get('url', 'Unknown')}")
                    continue

                point = {
                    "id": uuid.uuid4().hex,
                    "vector": article['embeddings'],
                    "payload": {k: article[k] for k in ['url', 'headline', 'paragraphs', 'source'] if k in article}
                }
                points.append(point)
                urls_to_update.append(article['url'])

            except json.JSONDecodeError:
                logger.error("Failed to decode JSON, skipping bad data.")
                continue

        if points:
            operation_info = qdrant_client.upsert(collection_name="articles", points=points)
            logger.info(f"Upsert operation completed: {operation_info}")

            if urls_to_update:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://postgres_service:5434/update_qdrant_flags",
                        json={"urls": urls_to_update}
                    )
                    if response.status_code == 200:
                        logger.info("Successfully updated Qdrant flags for articles.")
                    else:
                        logger.error(f"Failed to update Qdrant flags: {response.text}")

        return {"message": "Embeddings processed and stored in Qdrant."}

    except Exception as e:
        logger.error("An error occurred while storing embeddings: ", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# Searching for articles 
@app.get("/search")
async def search(query: str, top: int = 10):
    try:
        query_embeddings_response = httpx.get(f"http://nlp_service:420/generate_query_embeddings?query={query}")
        query_embeddings_response.raise_for_status()

        query_embeddings = query_embeddings_response.json().get('embeddings', [])
        if not query_embeddings:
            raise ValueError("No embeddings generated for query.")

        search_response = qdrant_client.search(
            collection_name="articles",
            query_vector=query_embeddings,
            limit=top,
            score_threshold=0.1,
        )

        # parse for htmx
        articles = [point.payload for point in search_response]  # Adjusted line
        # add point.score to the articles / changing response structure here from point with article and score to article with score object
        for article, point in zip(articles, search_response):
            article['score'] = point.score
        
        logger.info(f"Length of articles retrieved: {len(articles)}")

        return {"message": "Search successful", "data": articles}
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from NLP service: {str(e)}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
        