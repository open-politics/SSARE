import os
import json
import logging
from typing import List
from redis.asyncio import Redis
from fastapi import FastAPI
from openai import OpenAI
import instructor
from core.models import Article, ArticleTags, Tag, Entity, Location
from core.utils import UUIDEncoder
from pydantic import BaseModel, Field
from pydantic import validator, field_validator
from prefect import task, flow
from prefect_ray.task_runners import RayTaskRunner
from algoqual import algoqual
import time
import uuid
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from core.adb import get_session


async def lifespan(app):
    yield

# FastAPI app
app = FastAPI(lifespan=lifespan)

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


# Configure LiteLLM
my_proxy_api_key = "sk-1234"
my_proxy_base_url = "http://litellm:4000"


if os.getenv("LOCAL_LLM") == "True":
    client = instructor.from_openai(OpenAI(base_url=my_proxy_base_url, api_key=my_proxy_api_key))
else:
    client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

from pydantic import BaseModel, field_validator
from typing import List

from pydantic import BaseModel, field_validator
from typing import List, Dict, Any, Optional
import json

class NewsArticleClassification(BaseModel):
    title: str
    news_category: str
    secondary_categories: List[str]
    keywords: List[str]
    geopolitical_relevance: int
    legislative_influence_score: int
    international_relevance_score: int
    democratic_process_implications_score: int
    general_interest_score: int
    spam_score: int
    clickbait_score: int
    fake_news_score: int
    satire_score: int

    @field_validator('geopolitical_relevance', 'legislative_influence_score', 
                     'international_relevance_score', 'democratic_process_implications_score', 
                     'general_interest_score', 'spam_score', 'clickbait_score', 
                     'fake_news_score', 'satire_score', mode='before')
    def convert_to_int(cls, v):
        if isinstance(v, dict):
            v = v.get('score', 0)
        if isinstance(v, (float, str)):
            v = float(v)
        return min(max(int(v * 10), 1), 10)  # Convert to int 1-10

    @field_validator('secondary_categories', 'keywords', mode='before')
    def parse_string_to_list(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # If JSON parsing fails, split by comma as a fallback
                return [item.strip() for item in v.strip('[]').split(',')]
        return v

# Functions for LLM tasks

@task(retries=3)
async def classify_article(article: Article, schema_id: UUID) -> Dict[str, Any]:
    """Classify the article using LLM with a specific schema."""
    if schema_id not in algoqual.schemas:
        await algoqual.load_schemas()
    
    dynamic_model = algoqual.schemas[schema_id]
    prompt = algoqual.get_llm_prompt(schema_id)
    
    classification = await client.chat.completions.create(
        model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4o-2024-08-06",
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

@app.post("/classify_articles/{schema_name}")
async def classify_articles_endpoint(schema_name: str, batch_size: int = 50):
    schema = schema_manager.get_schema_by_name(schema_name)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Schema '{schema_name}' not found")

    articles = await retrieve_articles_from_redis(batch_size)
    processed_articles = []
    
    for article in articles:
        try:
            classification = await classify_article(article, schema.id)
            processed_article = {
                "url": article.url,
                "classification": classification,
                "schema_id": str(schema.id)
            }
            processed_articles.append(json.dumps(processed_article))
        except Exception as e:
            logger.error(f"Error processing article {article.url}: {str(e)}")
    
    if processed_articles:
        redis_conn = Redis(host='redis', port=6379, db=4)
        await redis_conn.rpush('articles_with_classification_queue', *processed_articles)
        await redis_conn.close()
    
    return {"message": f"Processed {len(processed_articles)} articles with schema {schema_name}"}

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

@flow
async def process_articles(batch_size: int = 50):
    """Process a batch of articles: retrieve, classify, and serialize them."""
    articles = await retrieve_articles_from_redis(batch_size=batch_size)
    
    if not articles:
        logger.warning("No articles to process.")
        return []
    
    logger.info(f"processing: {len(articles)} articles")
    
    processed_articles = []
    for article in articles:
        try:
            classification = await classify_article(article)
            
            # Combine article and classification data
            article_dict = article.dict()
            article_dict['classification'] = classification.dict()
            
            processed_articles.append(json.dumps(article_dict, cls=UUIDEncoder))
            print(classification)
            
            if os.getenv("LOCAL_LLM") == "True":
                time.sleep(2)
        except Exception as e:
            logger.error(f"Error processing article: {article}")
            logger.error(f"Error: {e}")
    
    if processed_articles:
        write_articles_to_redis(processed_articles)
    return processed_articles

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

@app.post("/classify_articles")
async def classify_articles_endpoint(batch_size: int = 50):
    logger.debug("Processing articles")
    processed_articles = await process_articles(batch_size)
    
    if not processed_articles:
        return {"message": "No articles processed."}
    
    return {
        "message": "Articles processed successfully",
        "processed_count": len(processed_articles),
        "processed_articles": processed_articles
    }

# Health endpoint
@app.get("/healthz")
def healthz():
    return {"status": "OK"}