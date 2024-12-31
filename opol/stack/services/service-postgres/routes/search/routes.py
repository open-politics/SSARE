import json
import logging
import math 
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Query, APIRouter
from sqlmodel import select
from contextlib import asynccontextmanager
import httpx

from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, func, or_, desc, distinct, exists
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from datetime import datetime
from core.adb import get_session
from core.models import Content, Entity, Location, ContentEvaluation, ContentEntity, ContentChunk, EntityLocation, ContentLocation
from core.service_mapping import config
from .models import SearchType
from core.utils import logger

from pydantic import BaseModel
import uuid
from datetime import datetime

from sqlalchemy.types import DateTime

from pydantic import BaseModel, field_validator


router = APIRouter()

##### Regular Articles Search
@router.get("/contents")
async def get_contents(
    url: Optional[str] = None,
    search_query: Optional[str] = None,
    search_type: SearchType = SearchType.TEXT,
    skip: Optional[int] = Query(0, description="Number of articles to skip"),
    limit: int = Query(10, description="Number of articles to return"),
    sort_by: Optional[str] = Query(None),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    filters: Optional[str] = Query(None, description="JSON string of filters"),
    session: AsyncSession = Depends(get_session),
    news_category: Optional[str] = Query(None, description="Filter by news category"),
    secondary_category: Optional[str] = Query(None, description="Filter by secondary category"),
    keyword: Optional[str] = Query(None, description="Filter by keyword"),
    entities: Optional[List[str]] = Query(None, description="PYTHON list of entities"),
    locations: Optional[str] = Query(None, description="Comma-separated list of locations"),
    topics: Optional[str] = Query(None, description="Comma-separated list of topics"),
    classification_scores: Optional[str] = Query(None, description="JSON string of classification score ranges"),
    keyword_weights: Optional[str] = Query(None, description="JSON string of keyword weights"),
    exclude_keywords: Optional[str] = Query(None, description="Comma-separated list of exclude keywords"),
    from_date: Optional[str] = Query(None, description="Start date for search"),
    to_date: Optional[str] = Query(None, description="End date for search"),
):
    try:
        # Parse filters and parameters
        filter_dict = json.loads(filters) if filters else {}
        entity_list = entities if entities else []
        location_list = locations.split(",") if locations else []
        topic_list = topics.split(",") if topics else []
        score_filters = json.loads(classification_scores) if classification_scores else {}
        keyword_weights_dict = json.loads(keyword_weights) if keyword_weights else {}
        exclude_keywords_list = exclude_keywords.split(",") if exclude_keywords else []

        async with session.begin():
            # Base query with eager loading
            query = select(Content).options(
                selectinload(Content.entities).selectinload(Entity.locations),
                selectinload(Content.tags),
                selectinload(Content.evaluation),
                selectinload(Content.media_details)
            )

            # Handle location-based filtering
            if location_list:
                # Create a subquery to get all content IDs related to the locations
                location_subquery = (
                    select(distinct(Content.id))
                    .select_from(Content)
                    .join(ContentEntity)
                    .join(Entity)
                    .join(EntityLocation)
                    .join(Location)
                    .where(Location.name.in_(location_list))
                )

                # Apply the subquery filter using EXISTS
                query = (
                    select(Content)
                    .options(
                        selectinload(Content.entities).selectinload(Entity.locations),
                        selectinload(Content.tags),
                        selectinload(Content.evaluation),
                        selectinload(Content.media_details)
                    )
                    .join(ContentEntity, Content.id == ContentEntity.content_id)
                    .join(Entity, ContentEntity.entity_id == Entity.id)
                    .join(EntityLocation, Entity.id == EntityLocation.entity_id)
                    .join(Location, EntityLocation.location_id == Location.id)
                    .where(Location.name.in_(location_list))
                    .distinct()
                )

                # Add logging to help debug
                logger.info(f"Location subquery: {location_subquery}")
                subquery_count = await session.execute(
                    select(func.count()).select_from(location_subquery.subquery())
                )
                matching_count = subquery_count.scalar()
                logger.info(f"Number of matching content IDs: {matching_count}")

            # Apply search based on search_type
            if search_query:
                if search_type == SearchType.TEXT:
                    search_condition = or_(
                        func.lower(Content.title).contains(func.lower(search_query)),
                        func.lower(Content.text_content).contains(func.lower(search_query)),
                        exists().where(
                            and_(
                                ContentEntity.content_id == Content.id,
                                Entity.id == ContentEntity.entity_id,
                                func.lower(Entity.name).contains(func.lower(search_query))
                            )
                        )
                    )
                    query = query.where(search_condition)
                elif search_type == SearchType.SEMANTIC:
                    try:
                        async with httpx.AsyncClient() as client:
                            response = await client.get(
                                f"{config.service_urls['service-embeddings']}/generate_query_embeddings",
                                params={"query": search_query}
                            )
                            response.raise_for_status()
                            query_embeddings = response.json()["embeddings"]
                            
                            # Modified query to include the distance in the SELECT list
                            query = (
                                select(
                                    Content,
                                    ContentChunk.embeddings.l2_distance(query_embeddings).label('distance')
                                )
                                .options(
                                    selectinload(Content.entities).selectinload(Entity.locations),
                                    selectinload(Content.tags),
                                    selectinload(Content.evaluation),
                                    selectinload(Content.media_details)
                                )
                                .join(ContentChunk, Content.id == ContentChunk.content_id)
                                .order_by('distance')  # Order by the labeled distance
                                .distinct()
                            )
                    except Exception as e:
                        logger.error(f"Semantic search error: {e}")
                        raise HTTPException(status_code=500, detail="Semantic search failed")

            # Apply basic filters
            if url:
                query = query.where(Content.url == url)

            # Apply category filters
            if news_category or secondary_category or keyword:
                category_conditions = []
                if news_category:
                    category_conditions.append(ContentEvaluation.news_category == news_category)
                if secondary_category:
                    category_conditions.append(ContentEvaluation.secondary_categories.any(secondary_category))
                if keyword:
                    category_conditions.append(ContentEvaluation.keywords.any(keyword))
                if category_conditions:
                    query = query.where(or_(*category_conditions))

            # Apply entity filters
            if entity_list:
                query = query.where(Entity.name.in_(entity_list))

            # Apply topic filters
            if topic_list:
                query = query.where(ContentEvaluation.secondary_categories.any(topic_list))

            # Apply classification score filters
            for score_type, score_range in score_filters.items():
                min_score, max_score = score_range
                query = query.where(
                    and_(
                        getattr(ContentEvaluation, score_type) >= min_score,
                        getattr(ContentEvaluation, score_type) <= max_score
                    )
                )

            # Apply keyword weights
            if keyword_weights_dict:
                for keyword, weight in keyword_weights_dict.items():
                    query = query.where(
                        or_(
                            Content.title.ilike(f'%{keyword}%') * weight,
                            Content.text_content.ilike(f'%{keyword}%') * weight
                        )
                    )

            # Apply exclusion keywords
            if exclude_keywords_list:
                for keyword in exclude_keywords_list:
                    query = query.where(
                        and_(
                            ~Content.title.ilike(f'%{keyword}%'),
                            ~Content.text_content.ilike(f'%{keyword}%')
                        )
                    )

            # Apply sorting
            if sort_by:
                sort_column = getattr(ContentEvaluation, sort_by, None)
                if sort_column:
                    query = query.order_by(desc(sort_column) if sort_order == "desc" else sort_column)

            # Execute query with pagination
            result = await session.execute(query.offset(skip).limit(limit))
            
            # Handle results differently based on search type
            if search_type == SearchType.SEMANTIC:
                contents = [row[0] for row in result.unique().all()]  # Get Content objects from tuples
            else:
                contents = result.unique().scalars().all()

            # Format response
            contents_data = []
            for content in contents:
                content_dict = {
                    "id": str(content.id),
                    "url": content.url,
                    "title": content.title,
                    "source": content.source,
                    "insertion_date": content.insertion_date if content.insertion_date else None,
                    "text_content": content.text_content,
                    "top_image": content.media_details.top_image if content.media_details else None,
                    "entities": [
                        {
                            "id": str(e.id),
                            "name": e.name,
                            "entity_type": e.entity_type,
                            "locations": [
                                {
                                    "name": loc.name,
                                    "location_type": loc.location_type,
                                    "coordinates": loc.coordinates.tolist() if loc.coordinates is not None else None
                                } for loc in e.locations
                            ] if e.locations else []
                        } for e in content.entities
                    ] if content.entities else [],
                    "tags": [
                        {
                            "id": str(t.id),
                            "name": t.name
                        } for t in (content.tags or [])
                    ],
                    "evaluation": content.evaluation.dict() if content.evaluation else None
                }
                contents_data.append(content_dict)

            return contents_data

    except ValueError as e:
        logger.error(f"Invalid value error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error retrieving contents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving contents")

###### Entities for Location
@router.get("/location_entities/{location_name}")
async def get_location_entities(
    location_name: str, 
    skip: int = 0, 
    limit: int = 50, 
    session: AsyncSession = Depends(get_session)
):
    try:
        # Subquery via EntityLocation
        subquery_entity = (
            select(Content.id)
            .join(ContentEntity, Content.id == ContentEntity.content_id)
            .join(Entity, ContentEntity.entity_id == Entity.id)
            .join(EntityLocation, Entity.id == EntityLocation.entity_id)
            .join(Location, EntityLocation.location_id == Location.id)
            .where(Location.name == location_name)
            .distinct()
        )

        # Subquery via ContentLocation
        subquery_content = (
            select(Content.id)
            .join(ContentLocation, Content.id == ContentLocation.content_id)
            .join(Location, ContentLocation.location_id == Location.id)
            .where(Location.name == location_name)
            .distinct()
        )

        # Combine both subqueries using UNION
        combined_subquery = subquery_entity.union(subquery_content).subquery()

        # Main query to get entities from the combined subquery
        query = (
            select(
                Entity.name,
                Entity.entity_type,
                func.count(distinct(Content.id)).label('article_count'),
                func.sum(ContentEntity.frequency).label('total_frequency')
            )
            .join(ContentEntity, Entity.id == ContentEntity.entity_id)
            .join(Content, ContentEntity.content_id == Content.id)
            .where(Content.id.in_(select(combined_subquery.c.id)))
            .group_by(Entity.id, Entity.name, Entity.entity_type)
        )

        result = await session.execute(query)
        entities = result.all()

        # Additional logging for debugging
        logger.debug(f"Entities found for location '{location_name}': {entities}")

        # Filter and calculate relevance score
        filtered_entities = []
        for e in entities:
            # Clean the name by removing possessives but maintain capitalization
            cleaned_name = e.name.replace("'s", "").replace("'ss", "")
            comparison_name = cleaned_name.lower()
            
            if comparison_name != location_name.lower():
                # Adjust relevance score calculation
                relevance_score = (e.total_frequency * math.log(e.article_count + 1))
                
                # Boost score for PERSON entities
                if e.entity_type == 'PERSON':
                    relevance_score *= 1.75
                
                filtered_entities.append({
                    "name": cleaned_name,  # Store cleaned name with original capitalization
                    "type": e.entity_type,
                    "article_count": e.article_count,
                    "total_frequency": e.total_frequency,
                    "relevance_score": relevance_score
                })

        # Merge similar entities
        merged_entities = {}
        for entity in filtered_entities:
            name_key = entity['name'].lower()  # Already cleaned of possessives
            found = False
            for key in merged_entities:
                if name_key in key or key in name_key:
                    # Merge the entities
                    merged_entities[key]['article_count'] += entity['article_count']
                    merged_entities[key]['total_frequency'] += entity['total_frequency']
                    merged_entities[key]['relevance_score'] += entity['relevance_score']
                    # Keep the longer cleaned name with proper capitalization
                    if len(entity['name']) > len(merged_entities[key]['name']):
                        merged_entities[key]['name'] = entity['name']
                    found = True
                    break
            if not found:
                merged_entities[name_key] = entity

        # Convert back to list and sort
        sorted_entities = sorted(merged_entities.values(), key=lambda x: x['relevance_score'], reverse=True)
        paginated_entities = sorted_entities[skip:skip+limit]

        logger.info(f"Query for location '{location_name}' returned {len(paginated_entities)} merged entities")

        return paginated_entities

    except Exception as e:
        logger.error(f"Error in get_location_entities: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

    finally:
        if not entities:
            # If no entities are found, let's check if the location exists
            location_check = await session.execute(select(Location).where(Location.name == location_name))
            location = location_check.scalar_one_or_none()
            if location:
                logger.info(f"Location '{location_name}' exists in the database but no related entities found")
            else:
                logger.warning(f"Location '{location_name}' does not exist in the database")

class MostRelevantEntitiesRequest(BaseModel):
    article_ids: List[str]
    skip: int = 0
    limit: int = 10

@router.post("/most_relevant_entities")
async def get_most_relevant_entities(
    request: MostRelevantEntitiesRequest,
    session: AsyncSession = Depends(get_session)
):
    try:
        # Convert article_ids to UUIDs
        article_uuids = [uuid.UUID(article_id) for article_id in request.article_ids]

        # Query to get entities related to the given article IDs
        query = (
            select(
                Entity.name,
                Entity.entity_type,
                func.count(distinct(Content.id)).label('article_count'),
                func.sum(ContentEntity.frequency).label('total_frequency')
            )
            .join(ContentEntity, Entity.id == ContentEntity.entity_id)
            .join(Content, ContentEntity.content_id == Content.id)
            .where(Content.id.in_(article_uuids))
            .group_by(Entity.id, Entity.name, Entity.entity_type)
        )

        result = await session.execute(query)
        entities = result.all()

        # Calculate relevance score and filter entities
        filtered_entities = []
        for e in entities:
            # Clean the name but maintain capitalization
            cleaned_name = e.name.replace("'s", "").replace("'ss", "")
            relevance_score = (e.total_frequency * math.log(e.article_count + 1))
            if e.entity_type == 'person':
                relevance_score *= 1.75

            filtered_entities.append({
                "name": cleaned_name,
                "type": e.entity_type,
                "article_count": e.article_count,
                "total_frequency": e.total_frequency,
                "relevance_score": relevance_score
            })

        # Merge similar entities
        merged_entities = {}
        for entity in filtered_entities:
            name_key = entity['name'].lower()  # Use lowercase for comparison
            found = False
            for key in merged_entities:
                if name_key in key or key in name_key:
                    merged_entities[key]['article_count'] += entity['article_count']
                    merged_entities[key]['total_frequency'] += entity['total_frequency']
                    merged_entities[key]['relevance_score'] += entity['relevance_score']
                    if len(entity['name']) > len(merged_entities[key]['name']):
                        merged_entities[key]['name'] = entity['name']
                    found = True
                    break
            if not found:
                merged_entities[name_key] = entity

        # Convert back to list and sort
        sorted_entities = sorted(merged_entities.values(), key=lambda x: x['relevance_score'], reverse=True)
        paginated_entities = sorted_entities[request.skip:request.skip+request.limit]

        logger.info(f"Returning {len(paginated_entities)} most relevant entities for given articles")

        return paginated_entities

    except Exception as e:
        logger.error(f"Error in get_most_relevant_entities: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


#### Articles By Entitiy
@router.get("/contents_by_entity/{entity_name}")
async def get_articles_by_entity(
    entity_name: str,
    skip: int = 0,
    limit: int = 10,
    session: AsyncSession = Depends(get_session)
    ):
    try:
        # Main query to get articles related to the entity with eager loading
        query = (
            select(Content)
            .options(
                selectinload(Content.entities).selectinload(Entity.locations),
                selectinload(Content.tags),
                selectinload(Content.evaluation),
                selectinload(Content.media_details)
            )
            .join(ContentEntity, Content.id == ContentEntity.content_id)
            .join(Entity, ContentEntity.entity_id == Entity.id)
            .where(Entity.name == entity_name)
            .distinct()
            .offset(skip)
            .limit(limit)
        )

        result = await session.execute(query)
        contents = result.unique().scalars().all()

        contents_data = []
        for content in contents:
            content_dict = {
                "id": str(content.id),
                "url": content.url,
                "title": content.title,
                "source": content.source,
                "insertion_date": content.insertion_date if content.insertion_date else None,
                "text_content": content.text_content,
                "top_image": content.media_details.top_image if content.media_details else None,
                "entities": [
                    {
                        "id": str(e.id),
                        "name": e.name,
                        "entity_type": e.entity_type,
                        "locations": [
                            {
                                "name": loc.name,
                                "location_type": loc.location_type,
                                "coordinates": loc.coordinates.tolist() if loc.coordinates is not None else None
                            } for loc in e.locations
                        ] if e.locations else []
                    } for e in content.entities
                ] if content.entities else [],
                "tags": [
                    {
                        "id": str(t.id),
                        "name": t.name
                    } for t in (content.tags or [])
                ],
                "evaluation": content.evaluation.dict() if content.evaluation else None
            }
            contents_data.append(content_dict)

        logger.info(f"Returning {len(contents_data)} articles for entity '{entity_name}'")
        return contents_data

    except Exception as e:
        logger.error(f"Error retrieving articles for entity '{entity_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving articles")


#### Articles By Location
@router.get("/contents_by_location/{location}")
async def get_articles_by_location(
    location: str,
    skip: int,
    limit: int,
    session: AsyncSession = Depends(get_session)
):
    try:
        async with session.begin():
            # Query to get contents and their associated locations
            query = (
                select(Content)
                .options(
                    selectinload(Content.entities).selectinload(Entity.locations),
                    selectinload(Content.tags),
                    selectinload(Content.evaluation),
                    selectinload(Content.media_details)
                )
                .join(ContentEntity, Content.id == ContentEntity.content_id)
                .join(Entity, ContentEntity.entity_id == Entity.id)
                .join(EntityLocation, Entity.id == EntityLocation.entity_id)
                .join(Location, EntityLocation.location_id == Location.id)
                .where(Location.name == location)
                .distinct()
                .offset(skip)
                .limit(limit)
            )

            result = await session.execute(query)
            contents = result.unique().scalars().all()
            logger.info(f"Retrieved {len(contents)} contents for location '{location}'")

            # Format response within the async context
            contents_data = []
            for content in contents:
                content_dict = {
                    "id": str(content.id),
                    "url": content.url,
                    "title": content.title,
                    "source": content.source,
                    "insertion_date": content.insertion_date if content.insertion_date else None,
                    "text_content": content.text_content,
                    "top_image": content.media_details.top_image if content.media_details else None,
                    "entities": [
                        {
                            "id": str(e.id),
                            "name": e.name,
                            "entity_type": e.entity_type,
                            "locations": [
                                {
                                    "name": loc.name,
                                    "location_type": loc.location_type,
                                    "coordinates": loc.coordinates.tolist() if loc.coordinates is not None else None
                                } for loc in e.locations
                            ] if e.locations else []
                        } for e in content.entities
                    ] if content.entities else [],
                    "tags": [
                        {
                            "id": str(t.id),
                            "name": t.name
                        } for t in (content.tags or [])
                    ],
                    "evaluation": content.evaluation.dict() if content.evaluation else None
                }
                contents_data.append(content_dict)

            # Reverse the list before returning
            contents_data.reverse()
            return contents_data

    except Exception as e:
        logger.error(f"Error retrieving articles for location '{location}': {e}")
        raise HTTPException(status_code=500, detail="Error retrieving articles")









from typing import List, Dict, Any
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from core.models import Content, ContentEntity, Entity, ContentEvaluation

@router.get("/time_series_entity_in_dimensions", response_model=None)
async def get_entity_time_relevance(
    entity: str,
    timeframe_from: str,
    timeframe_to: str,
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    try:
        # Query to get articles mentioning the entity within the timeframe
        query = (
            select(
                Content.insertion_date,
                func.sum(ContentEntity.frequency).label('total_weight'),
                func.array_agg(ContentEvaluation.topics).label('topics')
            )
            .join(ContentEntity, Content.id == ContentEntity.content_id)
            .join(Entity, ContentEntity.entity_id == Entity.id)
            .join(ContentEvaluation, Content.id == ContentEvaluation.content_id)
            .where(
                Entity.name == entity,
                Content.insertion_date.between(timeframe_from, timeframe_to)
            )
            .group_by(Content.insertion_date)
            .order_by(Content.insertion_date)
        )

        result = await session.execute(query)
        time_series_data = result.all()

        # Format the result as a list of dictionaries
        formatted_data = [
            {
                "date": row.insertion_date,
                "total_weight": row.total_weight,
                "topics": row.topics
            }
            for row in time_series_data
        ]

        return formatted_data

    except Exception as e:
        logger.error(f"Error in get_entity_time_relevance: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


class EntityScoreRequest(BaseModel):
    entity: str
    score_type: str
    timeframe_from: str
    timeframe_to: str

    @field_validator('timeframe_from', 'timeframe_to')
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')

@router.post("/entity_score_over_time")
async def entity_score_over_time(
    request: EntityScoreRequest,
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    try:
        # Convert string dates to datetime objects
        timeframe_from = datetime.strptime(request.timeframe_from, '%Y-%m-%d')
        timeframe_to = datetime.strptime(request.timeframe_to, '%Y-%m-%d')
        
        # Create the truncated date expression
        truncated_date = func.date_trunc(
            'day', 
            func.cast(Content.insertion_date, DateTime)
        ).label('date')
        
        query = (
            select(
                truncated_date,
                func.avg(getattr(ContentEvaluation, request.score_type)).label('average_score'),
                func.min(getattr(ContentEvaluation, request.score_type)).label('min_score'),
                func.max(getattr(ContentEvaluation, request.score_type)).label('max_score'),
                func.stddev(getattr(ContentEvaluation, request.score_type)).label('std_dev'),
                func.count(Content.id).label('article_count'),
                func.sum(ContentEntity.frequency).label('total_frequency'),
                func.avg(ContentEvaluation.sociocultural_interest).label('avg_interest'),
                func.array_agg(distinct(ContentEvaluation.event_type)).label('event_types'),
                func.array_agg(distinct(Content.source)).label('sources')
            )
            .join(ContentEvaluation, Content.id == ContentEvaluation.content_id)
            .join(ContentEntity, Content.id == ContentEntity.content_id)
            .join(Entity, ContentEntity.entity_id == Entity.id)
            .where(
                Entity.name == request.entity,
                func.cast(Content.insertion_date, DateTime).between(timeframe_from, timeframe_to)
            )
            .group_by(truncated_date)
            .order_by(truncated_date)
        )

        result = await session.execute(query)
        scores = result.all()

        # Format results...
        formatted_data = []
        for row in scores:
            entry = {
                "date": row.date.strftime("%Y-%m-%d"),
                "metrics": {
                    "average_score": float(row.average_score) if row.average_score is not None else None,
                    "min_score": float(row.min_score) if row.min_score is not None else None,
                    "max_score": float(row.max_score) if row.max_score is not None else None,
                    "standard_deviation": float(row.std_dev) if row.std_dev is not None else None
                },
                "context": {
                    "article_count": row.article_count,
                    "total_mentions": row.total_frequency,
                    "source_diversity": len(row.sources),
                    "sources": row.sources,
                    "event_types": row.event_types,
                    "sociocultural_interest": float(row.avg_interest) if row.avg_interest is not None else None
                },
                "reliability": {
                    "confidence_score": calculate_confidence_score(
                        article_count=row.article_count,
                        std_dev=row.std_dev,
                        source_count=len(row.sources)
                    )
                }
            }
            formatted_data.append(entry)

        return formatted_data

    except Exception as e:
        logger.error(f"Error in entity_score_over_time: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

def calculate_confidence_score(article_count: int, std_dev: float, source_count: int) -> float:
    """
    Calculate a confidence score based on article count, standard deviation, and source diversity.
    Returns a value between 0 and 1.
    """
    if std_dev is None:
        return 0.0
    
    # Base confidence on article count
    count_confidence = min(1.0, article_count / 10)
    
    # Standard deviation factor
    std_confidence = 1.0 / (1.0 + float(std_dev))
    
    # Source diversity factor
    source_confidence = min(1.0, source_count / 5)  # Max confidence at 5+ sources
    
    # Combine factors with weights
    confidence = (count_confidence * 0.4) + (std_confidence * 0.3) + (source_confidence * 0.3)
    
    return round(confidence, 2)

def calculate_quality_score(spam_score: float, fake_news_score: float, source_count: int) -> float:
    """
    Calculate a content quality score based on spam score, fake news score, and source diversity.
    Returns a value between 0 and 1.
    """
    if spam_score is None or fake_news_score is None:
        return 0.0
    
    # Inverse of spam and fake news scores (lower is better)
    spam_quality = 1 - (spam_score / 10)
    fake_news_quality = 1 - (fake_news_score / 10)
    
    # Source diversity factor
    source_quality = min(1.0, source_count / 5)
    
    # Combine factors with weights
    quality = (spam_quality * 0.4) + (fake_news_quality * 0.4) + (source_quality * 0.2)
    
    return round(quality, 2)

class TopEntitiesByScoreRequest(BaseModel):
    score_type: str
    timeframe_from: str
    timeframe_to: str
    limit: int = 10

@router.get("/top_entities_by_score")
async def top_entities_by_score(
    request: TopEntitiesByScoreRequest,
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    """
    Retrieves the top entities based on a specific score within a given timeframe.
    """
    try:
        # Validate score_type
        valid_scores = {
            'sociocultural_interest',
            'global_political_impact',
            'regional_political_impact',
            'global_economic_impact',
            'regional_economic_impact'
        }
        if score_type not in valid_scores:
            logger.error(f"Invalid score type: {request.score_type}")
            raise ValueError(f"Invalid score type: {request.score_type}")

        # Construct the query
        query = (
            select(
                Entity.name.label('entity_name'),
                func.avg(getattr(ContentEvaluation, request.score_type)).label('average_score'),
                func.count(Content.id).label('article_count')
            )
            .join(ContentEntity, Entity.id == ContentEntity.entity_id)
            .join(Content, ContentEntity.content_id == Content.id)
            .join(ContentEvaluation, Content.id == ContentEvaluation.content_id)
            .where(
                Content.insertion_date.between(timeframe_from, timeframe_to)
            )
            .group_by(Entity.id, Entity.name)
            .order_by(desc('average_score'))
            .limit(limit)
        )

        # Execute the query
        result = await session.execute(query)
        entities = result.all()

        # Format the result
        formatted_entities = [
            {
                "entity_name": row.entity_name,
                "average_score": round(row.average_score, 2) if row.average_score is not None else None,
                "article_count": row.article_count
            }
            for row in entities
        ]

        return formatted_entities

    except ValueError as ve:
        logger.error(f"ValueError in top_entities_by_score: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Error in top_entities_by_score: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")