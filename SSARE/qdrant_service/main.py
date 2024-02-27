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

from pydantic import BaseModel
from typing import List, Optional

class ArticleModel(BaseModel):
    url: str
    headline: str
    paragraphs: str  # JSON string
    source: Optional[str]
    embeddings: Optional[List[float]]
    embeddings_created: int = 1
    stored_in_qdrant: int = 0


app = FastAPI()

qdrant_client = QdrantClient(host='qdrant_storage', port=6333)
vectors_config = VectorParams(size=768, distance=Distance.COSINE)

# Try to create the collection if it does not exist, continue if it does
try:
    create_collection_info = qdrant_client.create_collection(
                    collection_name="articles",
                    vectors_config=vectors_config,
                )
    logger.info(f"Collection created: {create_collection_info}")
except Exception as e:
    logger.info(f"Collection already exists: {e}")
    pass
    
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
        points = []  # List to hold all points

        while True:
            articles_with_embedding_json = await redis_conn.rpop('articles_with_embeddings')
            if articles_with_embedding_json is None:
                logger.info("No more articles to process.")
                break

            article_with_embeddings = json.loads(articles_with_embedding_json)
            
            # Add a check to prevent re-processing if flag is already set
            if article_with_embeddings.get("stored_in_qdrant", 0) == 1:
                logger.info(f"Article already processed: {article_with_embeddings['url']}")
                continue

            try:
                validated_article = ArticleModel(**article_with_embeddings)
                logger.info(f"Validated article: {validated_article.url}")
                if validated_article.embeddings is not None:
                    logger.info(f"Embeddings: {validated_article.embeddings[:10]}")
                else:
                    logger.info("Embeddings are None")
            except Exception as e:
                logger.error(f"Error validating article: {e}")
                continue

            payload = {
                "headline": article_with_embeddings["headline"],
                "paragraphs": article_with_embeddings["paragraphs"],
                "source": article_with_embeddings["source"],
                "url": article_with_embeddings["url"],
            }

            # Log constructed payload (first 10 elements of each field)
            logger.info(f"Payload Url: {payload['url']}")
            logger.info(f"Payload Headline: {payload['headline']}")
            logger.info(f"Payload Text: {payload['paragraphs'][:3]}")
            logger.info(f"Payload Source: {payload['source']}")
            logger.info(f"Payload Length: {len(payload['paragraphs'])}")

            point = PointStruct(
                id=uuid.uuid4().hex,  # Use simple UUID string representation
                vector=article_with_embeddings["embeddings"],  # List of floats
                payload=payload
            )

            points.append(point)  # Add point to the list
            urls_to_update.append(validated_article.url)

        # Check if there are any points to upsert
        if points:
            # Upsert all points at once
            operation_info = qdrant_client.upsert(
                collection_name="articles",
                points=points,
            )

            logger.info(f"Upsert Operation: {operation_info}")

            # Update qdrant flags only if there are URLs to update
            if urls_to_update:
                logger.info(f"urls_to_update: {urls_to_update}")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                    "http://postgres_service:5434/update_qdrant_flags",
                    json={"urls": urls_to_update}
                    )
                    if response.status_code == 200:
                        logger.info("Updated qdrant flags for articles.")
                    else:
                        logger.error(f"Failed to update qdrant flags: {response.text}")

        return {"message": "Embeddings processed and stored in Qdrant."}
    except Exception as e:
        logger.error(f"Error storing embeddings: {e}")
        raise HTTPException(status_code=400, detail=str(e))



@app.get("/search")
async def search(query: str, top: int):
    try:
        # Convert textual query to embeddings
        logger.info(f"Query: {query}")
        logger.info(f"Top: {top}")
        query_embeddings_response = httpx.get(f"http://nlp_service:420/generate_query_embeddings?query={query}")
        query_embeddings_response.raise_for_status()  # Raises an HTTPException if the response was unsuccessful

        query_embeddings = query_embeddings_response.json()["embeddings"]
        logger.info(f"Query Embeddings: {query_embeddings[:10]}")  # Log the first 10 embeddings for debugging

        # Use the async search method
        search_response = qdrant_client.search(
            collection_name="articles",
            query_vector=query_embeddings,
            limit=top,
            score_threshold=0.1,
        )
        logger.info(f"Search Response: {search_response}")  # Log the search response for debugging

        return search_response
    except Exception as e:
        logger.error(f"Search error: {str(e)}")  # Log any exceptions for debugging
        raise HTTPException(status_code=400, detail=str(e))