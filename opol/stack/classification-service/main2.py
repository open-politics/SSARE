import os
import json
import logging
from typing import List, Optional
from redis import Redis
from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
from openai import OpenAI
import instructor
from classification_models import ContentEvaluation, ContentRelevance
from core.utils import UUIDEncoder, logger
from core.models import Content, ClassificationDimension, ContentEvaluation
from core.service_mapping import ServiceConfig
from classx import create_dynamic_classification_model, build_system_prompt
from pydantic import BaseModel, Field
# from prefect import flow, task
# from prefect.logging import get_run_logger
import time
from uuid import UUID
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from classx import classify_with_model
from core.adb import get_session
from core.service_mapping import get_redis_url
from sqlalchemy.orm import selectinload
import google.generativeai as genai
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError

app = FastAPI()
config = ServiceConfig()
model = "models/gemini-1.5-flash-latest"

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

# Configure LiteLLM
my_proxy_api_key = "sk-1234"
my_proxy_base_url = "http://litellm:4000"

# client = instructor.from_openai(OpenAI(api_key=os.getenv("OPENAI_API_KEY")))

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
client = instructor.from_gemini(
    client=genai.GenerativeModel(
        model_name="models/gemini-1.5-flash-latest", 
    ),
    mode=instructor.Mode.GEMINI_JSON,
)

# @task(retries=1)
def classify_content(content: Content) -> ContentRelevance:
    """Classify the content using LLM for relevance."""
    # logger = get_run_logger()
    # logger.info(f"Starting classification for content: {content.title}")
    
    response = classify_with_model(
        content=content,
        response_model=ContentRelevance,
        system_prompt="You are an AI assistant that analyzes articles for relevance.",
        user_content=f"Evaluate this article for relevance:\n\nHeadline: {content.title}\n\nContent: {content.text_content[:320]}"
    )
    
    logger.debug(f"Model response: {response}")
    
    return response

# @task(retries=1)
def evaluate_content(content: Content) -> ContentEvaluation:
    """Evaluate the content using LLM if it is relevant."""
    # logger = get_run_logger()
    # logger.info(f"Starting detailed evaluation for content: {content.title[:50]}...")
    
    response = classify_with_model(
        content=content,
        response_model=ContentEvaluation,
        system_prompt="You are an AI assistant that provides comprehensive evaluations.",
        user_content=f"Evaluate this article:\n\nHeadline: {content.title}\n\nContent: {content.text_content[:320]}"
    )
    
    return response

# @task
def retrieve_contents_from_redis(batch_size: int = 10) -> List[Content]:
    """Retrieve contents from Redis queue."""
    # logger = get_run_logger()
    # logger.info(f"Attempting to retrieve {batch_size} contents from Redis")
    
    redis_conn = Redis.from_url(get_redis_url(), db=4)
    _contents = redis_conn.lrange('contents_without_classification_queue', 0, batch_size - 1)
    redis_conn.ltrim('contents_without_classification_queue', batch_size, -1)

    if not _contents:
        logger.warning("No contents retrieved from Redis.")
        return []

    contents = []
    for content_data in _contents:
        try:
            content = Content(**json.loads(content_data))
            contents.append(content)
        except Exception as e:
            logger.error(f"Invalid content: {content_data}")
            logger.error(f"Error: {e}")

    logger.info(f"Successfully retrieved {len(contents)} contents")
    return contents


def write_contents_to_redis(serialized_contents):
    """Write serialized contents to Redis."""
    if not serialized_contents:
        logger.info("No contents to write to Redis")
        return

    serialized_contents = [json.dumps(content, cls=UUIDEncoder) if isinstance(content, dict) else content for content in serialized_contents]

    redis_conn_processed = Redis.from_url(get_redis_url(), db=4)
    redis_conn_processed.lpush('contents_with_classification_queue', *serialized_contents)
    logger.info(f"Wrote {len(serialized_contents)} contents with classification to Redis")


# @flow(log_prints=True)
def process_contents(batch_size: int = 10):
    """Process a batch of contents: retrieve, classify, and print them."""
    # logger = get_run_logger()
    contents = retrieve_contents_from_redis(batch_size=batch_size)

    if not contents:
        logger.warning("No contents to process.")
        return []

    logger.debug(f"Processing: {len(contents)} contents")

    evaluated_contents = []
    for content in contents:
        try:
            relevance = classify_content(content)
            logger.info(f"Relevance result: {relevance}")
            if relevance.type == "Other":
                logger.info(f"Content classified as irrelevant: {content.title[:50]}...")
                redis_conn = Redis(host='redis', port=config.REDIS_PORT, db=4)
                redis_conn.rpush('filtered_out_queue', json.dumps(content.dict(), cls=UUIDEncoder))
                continue
            else:
                # Use ContentEvaluation for relevant content
                llm_evaluation = evaluate_content(content)
                logger.info(f"Evaluation completed for: {content.title[:50]}")
                
                # Convert LLM evaluation to database model
                db_evaluation = ContentEvaluation(
                    content_id=content.id,
                    **llm_evaluation.dict()
                )
                
                # Create a clean dictionary with just the necessary data
                content_dict = {
                    'url': content.url,
                    'title': content.title,
                    'evaluations': db_evaluation.dict(exclude={'id'})
                }
                evaluated_contents.append(content_dict)
                
                if os.getenv("LOCAL_LLM") == "True":
                    time.sleep(2)
        except Exception as e:
            logger.error(f"Error processing content: {content.title[:50]}...")
            logger.error(f"Error: {e}")
    
    if evaluated_contents:
        logger.info(f"Writing {len(evaluated_contents)} evaluated contents to Redis")
        write_contents_to_redis(evaluated_contents)
    return evaluated_contents

@app.post("/classify_contents")
def classify_contents_endpoint(batch_size: int = 10):
    evaluated_contents = process_contents(batch_size)
    return {"evaluations": evaluated_contents}

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

    # @task(retries=3)
    def split_query_task(query: str) -> QueryResult:
        response = client.chat.completions.create(
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

# Define classification dimension model
class EntityClassificationDimension(BaseModel):
    name: str
    type: str
    description: Optional[str] = None

class EntityClassificationRequest(BaseModel):
    dimensions: List[EntityClassificationDimension]
    text: str

@app.post("/classify")
async def classify(request: EntityClassificationRequest):
    try:
        # Create dynamic classification model
        dimensions = [EntityClassificationDimension(**dim.dict()) for dim in request.dimensions]
        DynamicClassificationModel = create_dynamic_classification_model(dimensions)
        
        # Build system prompt
        system_prompt = build_system_prompt(dimensions)
        
        # Prepare user content
        user_content = request.text
        
        # Classify with model
        classification_result = classify_with_model(
            client=client,
            response_model=DynamicClassificationModel,
            system_prompt=system_prompt,
            user_content=user_content
        )
        
        return classification_result.dict()
    except Exception as e:
        logging.error(f"Classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class DynamicClassificationRequest(BaseModel):
    dimensions: List[EntityClassificationDimension]
    texts: str

@app.post("/classify_dynamic")
def classify_dynamic(request: DynamicClassificationRequest):
    # Create dynamic classification model
    try:
        dimensions = [EntityClassificationDimension(**dim.dict()) for dim in request.dimensions]
        DynamicClassificationModel = create_dynamic_classification_model(dimensions)
        
        # Build system prompt
        system_prompt = build_system_prompt(dimensions)


        
        user_content = f"Text: {request.texts}\n\n"
        classification_result = classify_with_model(
            client=client,
            response_model=DynamicClassificationModel,
            system_prompt=system_prompt,
            user_content=user_content
        )
        return classification_result.dict()
    except Exception as e:
        logging.error(f"Classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def retrieve_similar_entities(entity_name: str, session: AsyncSession):
    try:
        # Use plainto_tsquery for better handling of spaces and special characters
        tsquery = func.plainto_tsquery(entity_name)
        
        # Construct the query
        similar_entities_stmt = select(Entity.id, Entity.name, Entity.entity_type).where(
            Entity.entity_type == 'LOC',
            Entity.id != some_uuid,
            Entity.name.op('@@')(tsquery),
            func.similarity(Entity.name, entity_name) > 0.3
        ).limit(5)
        
        # Execute the query
        result = await session.execute(similar_entities_stmt)
        return result.fetchall()
    
    except SQLAlchemyError as e:
        logging.error(f"Database error: {e}")
        raise

# Example usage in your main function
async def process_entity(entity):
    async with AsyncSession() as session:
        similar_entities = await retrieve_similar_entities(entity.name, session)
        # Process similar_entities as needed