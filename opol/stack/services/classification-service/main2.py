import os
import json
import logging
from typing import List, Optional, Type
from redis import Redis
from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
from core.utils import UUIDEncoder, logger
from core.models import Content
from core.service_mapping import ServiceConfig
from pydantic import BaseModel, Field
import time
from uuid import UUID
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.adb import get_session
from core.service_mapping import get_redis_url
from sqlalchemy.orm import selectinload
import google.generativeai as genai
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from typing import Union
from fastclass import FastClass

app = FastAPI()
config = ServiceConfig()
model = "models/gemini-1.5-flash-latest"

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

# Initialize FastClass
xclass = FastClass("gemini-1.5-flash-latest")

# Define dynamic classification request model
class DynamicClassificationRequest(BaseModel):
    response_type: Union[str, Type[BaseModel]]
    prompt: str
    input_text: str

@app.post("/classify")
async def classify(request: DynamicClassificationRequest):
    logger.info(f"Classifying request with type: {request.response_type}")
    try:
        classification_result = xclass.infer(request.response_type, request.prompt, request.input_text)
        return classification_result
    except Exception as e:
        logging.error(f"Classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Example endpoint using Pydantic model directly
class ClassificationResult(BaseModel):
    relevant: bool
    relevance_level: int



@app.post("/classify_model")
def classify_model(prompt: str, input_text: str):
    try:
        classification_result = xclass.infer(ClassificationResult, prompt, input_text)
        return classification_result.model_dump()
    except Exception as e:
        logger.error(f"Classification error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

async def retrieve_similar_contents(content_text: str, session: AsyncSession):
    try:
        tsquery = func.plainto_tsquery(content_text)
        similar_contents_stmt = select(Content.id, Content.text, Content.type).where(
            Content.text.op('@@')(tsquery),
            func.similarity(Content.text, content_text) > 0.3
        ).limit(5)
        result = await session.execute(similar_contents_stmt)
        return result.fetchall()
    except SQLAlchemyError as e:
        logging.error(f"Database error: {e}")
        raise

# Health endpoint
@app.get("/healthz")
def healthz():
    return {"status": "OK"}

@app.get("/location_from_query")
def get_location_from_query(query: str):
    class LocationFromQuery(BaseModel):
        """Return the location name most relevant to the query."""
        location: str

    try:
        response = xclass.infer(LocationFromQuery, "Determine the most relevant location based on the query.", query)
        return response.location
    except Exception as e:
        logger.error(f"Error in location_from_query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

from enum import Enum

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

    Perform query expansion. If there are multiple common ways of phrasing a user question 
    or common synonyms for key words in the question, make sure to return multiple versions 
    of the query with the different phrasings.

    If there are acronyms or words you are not familiar with, do not try to rephrase them.
    Aim for 3-5 search queries.
    """
    search_queries: Union[List[str], str, dict]

class QueryResult(BaseModel):
    """
    The result of the query.
    If it's entity-related, return the entities in the query.
    """
    query_type: QueryType
    geo_distribution: GeoDistribution
    search_queries: SearchQueries
    entities: Optional[List[str]] = None

@app.get("/split_query")
def split_query(query: str):
    logger.info(f"Splitting query: {query}")

    def split_query_task(query: str) -> QueryResult:
        try:
            response = xclass.infer(QueryResult, "Analyze and split the query into its components.", query)
            return response.model_dump()
        except Exception as e:
            logger.error(f"Error splitting query: {e}")
            raise
    
    return split_query_task(query)