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
from pydantic import validator, field_validator
from prefect import task, flow
from prefect_ray.task_runners import RayTaskRunner

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI()

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
from typing import List
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
def classify_article(article: Article) -> NewsArticleClassification:
    """Classify the article using LLM."""
    return client.chat.completions.create(
        model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4o-2024-08-06",
        response_model=NewsArticleClassification,
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant that analyzes articles and provides tags and metrics. You are assessing the article for relevance to an open source political intelligence service. Create classifications suitable for category, issue area, topic, and top story. The metrics should be relevant to the article and the political intelligence service."
            },
            {
                "role": "user",
                "content": f"Analyze this article and provide tags and metrics:\n\nHeadline: {article.headline}\n\nContent: {article.paragraphs if os.getenv('LOCAL_LLM') == 'False' else article.paragraphs[:350]}",
            },
        ],
    )

@task
def retrieve_articles_from_redis(batch_size: int = 50) -> List[Article]:
    """Retrieve articles from Redis queue."""
    redis_conn = Redis(host='redis', port=6379, db=4)
    _articles = redis_conn.lrange('articles_without_classification_queue', 0, batch_size - 1)
    redis_conn.ltrim('articles_without_classification_queue', batch_size, -1)
    
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
    
    logger.info(f"processing: {len(articles)} articles")
    
    processed_articles = []
    for article in articles:
        try:
            classification = classify_article(article)
        
            processed_articles.append({
                "article": article,
                "classification": classification
            })
            print(classification)
            
            if os.getenv("LOCAL_LLM") == "True":
                sleep(2)
            else:
                continue
        except Exception as e:
            logger.error(f"Error processing article: {article}")
            logger.error(f"Error: {e}")
    
    write_articles_to_redis(processed_articles)
    return processed_articles

@task
def write_articles_to_redis(processed_articles):
    redis_conn_processed = Redis(host='redis', port=6379, db=4)
    serialized_articles = [json.dumps(article) for article in processed_articles]
    if serialized_articles:  # Check if the list is not empty
        redis_conn_processed.lpush('articles_with_classification_queue', *serialized_articles)
        logger.info(f"Wrote {len(processed_articles)} articles with classification to Redis")
    else:
        logger.info("No articles to write to Redis")

@app.post("/classify_articles")
def classify_articles_endpoint(batch_size: int = 2):
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