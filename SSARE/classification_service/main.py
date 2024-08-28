import os
import json
import logging
from typing import List, Dict, Any
from redis.asyncio import Redis
from fastapi import FastAPI, HTTPException
from openai import OpenAI
import instructor
from core.models import Article, ArticleTags, Tag, Entity, Location, DynamicClassification
from core.utils import UUIDEncoder
from pydantic import BaseModel, Field
from prefect import task, flow
from prefect_ray.task_runners import RayTaskRunner
import time
import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from core.adb import get_session
from core.classification_schema_manager import ClassificationSchemaManager, ClassificationSchema

schema_manager = ClassificationSchemaManager()
schema_manager.load_schemas()
from algoqual import algoqual


async def lifespan(app):
    algoqual.load_schemas()
    yield

# FastAPI app
app = FastAPI(lifespan=lifespan)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

schema_manager = ClassificationSchemaManager()

# Configure LiteLLM
my_proxy_api_key = "sk-1234"
my_proxy_base_url = "http://litellm:4000"

if os.getenv("LOCAL_LLM") == "True":
    client = instructor.from_openai(OpenAI(base_url=my_proxy_base_url, api_key=my_proxy_api_key))
else:
    client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

@task(retries=3)
async def classify_article(article: Article, schema_id: uuid.UUID) -> Dict[str, Any]:
    """Classify the article using LLM with a specific schema."""
    if schema_id not in algoqual.schemas:
        await algoqual.load_schemas()
    
    dynamic_model = algoqual.schemas[schema_id]
    prompt = algoqual.get_llm_prompt(schema_id)
    
    classification = await client.chat.completions.create(
        model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4-0613",
        response_model=dynamic_model,
        max_retries=2,
        messages=[
            {
                "role": "system",
                "content": prompt
            },
            {
                "role": "user",
                "content": f"Analyze this article and provide tags and metrics:\n\nHeadline: {article.headline}\n\nContent: {article.paragraphs if os.getenv('LOCAL_LLM') == 'False' else article.paragraphs[:350]}, be very critical.",
            },
        ],
    )
    
    return classification.dict()

@task
async def retrieve_articles_from_redis(batch_size: int = 50) -> List[Article]:
    """Retrieve articles from Redis queue."""
    redis_conn = Redis(host='redis', port=6379, db=4)
    _articles = await redis_conn.lrange('articles_without_classification_queue', 0, batch_size - 1)
    await redis_conn.ltrim('articles_without_classification_queue', batch_size, -1)
    
    if not _articles:
        logger.warning("No articles retrieved from Redis.")
        return []
    
    articles = []
    for article_data in _articles:
        try:
            article_dict = json.loads(article_data)
            article = Article(**article_dict)
            articles.append(article)
        except Exception as e:
            logger.error(f"Invalid article: {article_data}")
            logger.error(f"Error: {e}")
    
    await redis_conn.close()
    return articles

@task
async def write_articles_to_redis(serialized_articles):
    """Write serialized articles to Redis."""
    if not serialized_articles:
        logger.info("No articles to write to Redis")
        return

    redis_conn_processed = Redis(host='redis', port=6379, db=4)
    await redis_conn_processed.lpush('articles_with_classification_queue', *serialized_articles)
    await redis_conn_processed.close()
    logger.info(f"Wrote {len(serialized_articles)} articles with classification to Redis")

@app.post("/classify_articles/{schema_id}")
async def classify_articles_endpoint(schema_id: uuid.UUID, batch_size: int = 50):
    schema = schema_manager.get_schema(schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Schema with id '{schema_id}' not found")

    articles = await retrieve_articles_from_redis(batch_size)
    processed_articles = []
    
    for article in articles:
        try:
            classification = await classify_article(article, schema_id)
            processed_article = {
                "url": article.url,
                "classification": classification,
                "schema_id": schema_id
            }
            processed_articles.append(json.dumps(processed_article))
        except Exception as e:
            logger.error(f"Error processing article {article.url}: {str(e)}")
    
    if processed_articles:
        await write_articles_to_redis(processed_articles)
    
    return {"message": f"Processed {len(processed_articles)} articles with schema {schema_id}"}

@app.post("/create_schema_from_description")
async def create_schema_from_description(description: str):
    try:
        schema = await client.chat.completions.create(
            model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4-0613",
            response_model=ClassificationSchema,
            messages=[
                {"role": "system", "content": "Create a classification schema based on the following description."},
                {"role": "user", "content": description},
            ],
        )
        schema_id = await schema_manager.create_schema(schema)
        return {"message": "Schema created successfully", "schema_id": schema_id}
    except Exception as e:
        logger.error(f"Error creating schema: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/classify_articles_batch")
async def batch_process_endpoint(batch_size: int = 50):
    schemas = schema_manager.get_all_schemas()
    logger.error(f"Found {len(schemas)} schemas")
    if not schemas:
        raise HTTPException(status_code=404, detail="No classification schemas found")

    articles = await retrieve_articles_from_redis(batch_size)
    processed_articles = []

    for article in articles:
        article_classifications = []
        for schema in schemas:
            try:
                classification = await classify_article(article, schema.id)
                article_classifications.append({
                    "schema_id": schema.id,
                    "classification": classification
                })
            except Exception as e:
                logger.error(f"Error processing article {article.url} with schema {schema.id}: {str(e)}")

        if article_classifications:
            processed_article = {
                "url": article.url,
                "classifications": article_classifications
            }
            processed_articles.append(json.dumps(processed_article))

    if processed_articles:
        await write_articles_to_redis(processed_articles)

    return {"message": f"Batch processed {len(processed_articles)} articles with {len(schemas)} schemas"}

@app.get("/healthz")
def healthz():
    return {"status": "OK"}