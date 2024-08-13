import os
import json
import logging
from typing import List
from redis import Redis
from fastapi import FastAPI
from pydantic import BaseModel, Field
from openai import OpenAI
import instructor
from core.models import Article, ArticleTags, Tag, Entity, Location
from pydantic import validator
from prefect import task, flow
from prefect_ray.task_runners import RayTaskRunner

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI()

# Configure LLM
my_proxy_api_key = "sk-1234"
my_proxy_base_url = "http://litellm:4000"

if os.getenv("LOCAL_LLM") == "True":
    client = instructor.from_openai(OpenAI(base_url=my_proxy_base_url, api_key=my_proxy_api_key))
else:
    client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

class ArticleTag(BaseModel):
    name: str

class ArticleSentiment(BaseModel):
    name: str
    value: float

class PoliticalDimension(BaseModel):
    name: str
    value: float

class ArticleMetric(BaseModel):
    name: str
    value: float

class ArticleGeoPoliticsRelevance(BaseModel):
    relevance: float

# Pydantic models for LLM output
class ArticleClassification(BaseModel):
    tags: List[ArticleTag]
    metrics: List[ArticleMetric]
    sentiment: List[ArticleSentiment]
    political_dimensions: List[PoliticalDimension]
    relevance: ArticleGeoPoliticsRelevance

    @validator('tags', 'metrics', 'sentiment', 'political_dimensions', 'relevance', pre=True)
    def parse_json_string(cls, v):
        if isinstance(v, str):
            return json.loads(v)
        return v

# Functions for LLM tasks

@task(retries=3)
def classify_article(article: Article) -> ArticleClassification:
    """Classify the article using LLM."""
    return client.chat.completions.create(
        model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4",
        response_model=ArticleClassification,
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant that analyzes articles and provides tags and metrics. You are assessing the article for relevance to an open source political intelligence service. Create classifications suitable for category, issue area, topic, and top story. The metrics should be relevant to the article and the political intelligence service."
            },
            {
                "role": "user",
                "content": f"Analyze this article and provide tags and metrics:\n\nHeadline: {article.headline}\n\nContent: {article.paragraphs}",
            },
        ],
    )

@task
def retrieve_articles_from_redis(batch_size: int = 50) -> List[Article]:
    """Retrieve articles from Redis queue."""
    redis_conn = Redis(host='redis', port=6379, db=3)
    _articles = redis_conn.lrange('articles_without_tags_queue', 0, batch_size - 1)
    redis_conn.ltrim('articles_without_tags_queue', batch_size, -1)
    
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
    
    return articles

@flow
def process_articles(batch_size: int = 50):
    """Process a batch of articles: retrieve and classify them."""
    articles = retrieve_articles_from_redis(batch_size=batch_size)
    
    if not articles:
        logger.warning("No articles to process.")
        return []
    
    processed_articles = []
    for article in articles:
        classification = classify_article(article)
        
        processed_articles.append({
            "article": article,
            "classification": classification
        })
        print(classification)
    
    # write_articles_to_redis(processed_articles)
    return processed_articles

@task
def write_articles_to_redis(processed_articles):
    redis_conn_processed = Redis(host='redis', port=6379, db=3)
    serialized_articles = [json.dumps(article) for article in processed_articles]
    if serialized_articles:  # Check if the list is not empty
        redis_conn_processed.lpush('articles_with_embeddings', *serialized_articles)
        logger.info(f"Wrote {len(processed_articles)} articles with embeddings to Redis")
    else:
        logger.info("No articles to write to Redis")

@app.post("/process_articles")
def process_articles_endpoint(batch_size: int = 2):
    logger.debug("Processing articles")
    processed_articles = process_articles(batch_size)
    
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