import os
import json
import logging
from typing import List
from redis import Redis
from fastapi import FastAPI
from contextlib import asynccontextmanager
from openai import OpenAI
import instructor
from core.models import Article, ArticleTags, Tag, Entity, Location
from core.utils import UUIDEncoder, logger
from core.service_mapping import ServiceConfig
from pydantic import BaseModel, Field
from pydantic import validator, field_validator
from prefect import flow, task
import time
from uuid import UUID
from pydantic import BaseModel, field_validator
from typing import List

app = FastAPI()
config = ServiceConfig()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

# Configure LiteLLM
my_proxy_api_key = "sk-1234"
my_proxy_base_url = "http://litellm:4000"

if os.getenv("LOCAL_LLM") == "True":
    client = instructor.from_openai(OpenAI(base_url=my_proxy_base_url, api_key=my_proxy_api_key))
else:
    client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

# Extraction Data Model
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
    event_type: str

    @field_validator('geopolitical_relevance', 'legislative_influence_score', 
                     'international_relevance_score', 'democratic_process_implications_score', 
                     'general_interest_score', 'spam_score', 'clickbait_score', 
                     'fake_news_score', 'satire_score', mode='before')
    def ensure_int_range(cls, v):
        if not isinstance(v, int):
            raise ValueError(f"Value {v} is not an integer")
        if not (0 <= v <= 10):
            raise ValueError(f"Value {v} is out of range (1-10)")
        return v

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
@task(retries=1)
def classify_article(article: Article) -> NewsArticleClassification:
    """Classify the article using LLM."""
    return client.chat.completions.create(
        model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4o-2024-08-06",
        response_model=NewsArticleClassification,
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant that analyzes articles and provides tags and metrics. You are assessing the article for relevance to an open source political intelligence service. Create classifications suitable for category, issue area, topic, and top story. The metrics should be relevant to the article and the political intelligence service, ensuring that the values provided are carefully weighted and not overly extreme. You are also tasked with determining the event type of the article, which can be one of the following: 'Protests', 'Elections', 'Economic', 'Legal', 'Social', 'Crisis', 'War', 'Peace', 'Diplomacy', 'Technology', 'Science', 'Culture', 'Sports', 'Other'. The event type should be a single word or phrase that describes the main topic or theme of the article."
            },
            {
                "role": "user",
                "content": f"Analyze this article and provide tags and metrics:\n\nHeadline: {article.headline}\n\nContent: {article.paragraphs if os.getenv('LOCAL_LLM') == 'False' else article.paragraphs[:350]}, be very critical.",
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
    """Process a batch of articles: retrieve, classify, and serialize them."""
    articles = retrieve_articles_from_redis(batch_size=batch_size)
    
    if not articles:
        logger.warning("No articles to process.")
        return []
    
    logger.info(f"processing: {len(articles)} articles")
    
    processed_articles = []
    for article in articles:
        try:
            classification = classify_article(article)
            
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

# @task
def write_articles_to_redis(serialized_articles):
    """Write serialized articles to Redis."""
    if not serialized_articles:
        logger.info("No articles to write to Redis")
        return

    redis_conn_processed = Redis(host='redis', port=6379, db=4)
    redis_conn_processed.lpush('articles_with_classification_queue', *serialized_articles)
    logger.info(f"Wrote {len(serialized_articles)} articles with classification to Redis")

@app.post("/classify_articles")
def classify_articles_endpoint(batch_size: int = 50):
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


@app.get("/location_from_query")
def get_location_from_query(query: str):

    class LocationFromQuery(BaseModel):
        """Return the location name most relevant to the query."""
        location: str

    response = client.chat.completions.create(
        model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4o-2024-08-06",
        response_model=LocationFromQuery,
        messages=[
            {"role": "system", "content": "You are an AI assistant embedded as a function in a larger application. You are given a query and you need to return the location name most relevant to the query. Your response should be geo-codable to a region, city, town, country or continent."},
            {"role": "user", "content": f"The query is: {query}"}
        ],
    )
    return response.location


from enum import Enum
from typing import Union, Optional 

@app.get("/split_query")
def split_query(query: str):

    logger.info(f"Splitting query: {query}")

    class QueryType(Enum):
        International_Politics = "International Politics"
        Entity_Related = "Entity Related"
        Location_Related = "Location Related"
        Topic = "Topic"


        General = "General"

    class GeoDistribution(BaseModel):
        """
        The main location is where we want to zoom to. The secondary location is the list of countries tangent to the query.
        """
        main_location: str
        secondary_locations: List[str]
    
    class SearchQueries(BaseModel):
        """
        Represents a collection of search queries tailored for prompt engineering.
        This includes a primary natural language query, which is used to retrieve its closest vector snippets.
        Additionally, it encompasses a set of semantic queries designed to augment the primary query, aiming to gather complementary information.
        The goal is to simulate the retrieval of the most relevant and recent context information that a political intelligence analyst would seek through semantic search query retrieval.

        Perform query expansion. If there are multiple common ways of phrasing a user question \
        or common synonyms for key words in the question, make sure to return multiple versions \
        of the query with the different phrasings.

        If there are acronyms or words you are not familiar with, do not try to rephrase them.
        Aim for 3-5 search queries.
        
        """
        search_queries: Union[List[str], str, dict]
    
    class QueryResult(BaseModel):
        """
        The result of the query.
        If its entity related, return the entities in the query.
        """
        query_type: QueryType
        geo_distribution: GeoDistribution
        search_queries: SearchQueries
        entities: Optional[List[str]] = None

    @task(retries=3)
    def split_query_task(query: str) -> QueryResult:
        response = client.chat.completions.create(
            model="llama3.1" if os.getenv("LOCAL_LLM") == "True" else "gpt-4o-2024-08-06",
            response_model=QueryResult,
            messages=[
                {"role": "system", "content": "You are a political intelligence AI."},
                {"role": "user", "content": f"The query is: {query}"}
            ],
        )
        return response.dict()

    return split_query_task(query)

    # class CombinedQuery(BaseModel):
    #     """
    #     The primary query is a natural language query. It's closest snippets of vectors will be retrieved.
    #     The primary query is extended through several other semantic queryies, they aim to perform retrieval towards complementary information to the same query.

    #     This is supported by method queries. Choosing from the following options:
    #     - "entity retrieval"
    #     - "topic retrieval"
    #     - "location retrieval"
    #     """
    #     original_query: str
    #     combined_queries: List[str]

    # class CombinedQueryResult(BaseModel):
    #     """
    #     The result of the combined query.
    #     """
    #     primary_query: str
    #     combined_queries: List[str]






