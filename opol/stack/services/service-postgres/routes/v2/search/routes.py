import json
import logging
import math
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_, desc, func, select, exists, distinct
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, field_validator

from core.adb import get_session
from core.models import (
    Content,
    Entity,
    Location,
    ContentEvaluation,
    ContentEntity,
    EntityLocation,
    ContentChunk
)
from core.service_mapping import config
from core.utils import logger

router = APIRouter()


# ----------------------------
# Pydantic Models for Queries
# ----------------------------
class SearchType(str, Enum):
    TEXT = "text"
    SEMANTIC = "semantic"

class ContentsQueryParams(BaseModel):
    url: Optional[str] = None
    search_query: Optional[str] = None
    search_type: Optional[str] = None
    skip: Optional[int] = 0
    limit: int = 10
    sort_by: Optional[str] = None
    sort_order: str = "desc"
    filters: Optional[str] = None
    news_category: Optional[str] = None
    secondary_category: Optional[str] = None
    keyword: Optional[str] = None
    entities: Optional[str] = None
    locations: Optional[str] = None
    topics: Optional[str] = None
    classification_scores: Optional[str] = None
    keyword_weights: Optional[str] = None
    exclude_keywords: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None

    @field_validator('from_date', 'to_date', mode='before')
    def validate_date(cls, v):
        if v:
            try:
                return datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                raise ValueError('Date must be in YYYY-MM-DD format')
        return v


class MostRelevantEntitiesRequest(BaseModel):
    article_ids: List[str]
    skip: int = 0
    limit: int = 10


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


class TopEntitiesByScoreRequest(BaseModel):
    score_type: str
    timeframe_from: str
    timeframe_to: str
    limit: int = 10

    @field_validator('timeframe_from', 'timeframe_to')
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, '%Y-%m-%d')
            return v
        except ValueError:
            raise ValueError('Date must be in YYYY-MM-DD format')


# ----------------------------
# Helper Functions
# ----------------------------

async def get_semantic_embeddings(query: str) -> list:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{config.service_urls['service-embeddings']}/generate_query_embeddings",
                params={"query": query}
            )
            response.raise_for_status()
            return response.json()["embeddings"]
    except Exception as e:
        logger.error(f"Semantic search error: {e}")
        raise HTTPException(status_code=500, detail="Semantic search failed")


def apply_date_filters(query, from_date: Optional[datetime], to_date: Optional[datetime]):
    if from_date and to_date:
        return query.where(Content.insertion_date.between(from_date, to_date))
    elif from_date:
        return query.where(Content.insertion_date >= from_date)
    elif to_date:
        return query.where(Content.insertion_date <= to_date)
    return query


def apply_search_filters(query, search_query: Optional[str], search_type: SearchType):
    if not search_query:
        return query

    if search_type.lower() == 'text':
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
        return query.where(search_condition)
    elif search_type.lower() == 'semantic':
        embeddings = asyncio.run(get_semantic_embeddings(search_query))
        # Modify the query to include distance calculation
        return (
            select(
                Content,
                ContentChunk.embeddings.l2_distance(embeddings).label('distance')
            )
            .options(
                selectinload(Content.entities).selectinload(Entity.locations),
                selectinload(Content.tags),
                selectinload(Content.evaluation),
                selectinload(Content.media_details)
            )
            .join(ContentChunk, Content.id == ContentChunk.content_id)
            .order_by('distance')
            .distinct()
        )
    return query


def apply_common_filters(query, params: ContentsQueryParams):
    if params.url:
        query = query.where(Content.url == params.url)

    # Category Filters
    category_conditions = []
    if params.news_category:
        category_conditions.append(ContentEvaluation.news_category == params.news_category)
    if params.secondary_category:
        category_conditions.append(ContentEvaluation.secondary_categories.any(params.secondary_category))
    if params.keyword:
        category_conditions.append(ContentEvaluation.keywords.any(params.keyword))
    if category_conditions:
        query = query.where(or_(*category_conditions))

    # Entity Filters
    if params.entities:
        entity_list = params.entities.split(",")
        query = query.where(Entity.name.in_(entity_list))

    # Location Filters
    if params.locations:
        location_list = params.locations.split(",")
        query = query.where(Location.name.in_(location_list))

    # Topic Filters
    if params.topics:
        topic_list = params.topics.split(",")
        query = query.where(ContentEvaluation.secondary_categories.any(topic_list))

    # Classification Score Filters
    if params.classification_scores:
        score_filters = json.loads(params.classification_scores)
        for score_type, score_range in score_filters.items():
            min_score, max_score = score_range
            query = query.where(
                and_(
                    getattr(ContentEvaluation, score_type) >= min_score,
                    getattr(ContentEvaluation, score_type) <= max_score
                )
            )

    # Keyword Weights
    if params.keyword_weights:
        keyword_weights_dict = json.loads(params.keyword_weights)
        for keyword, weight in keyword_weights_dict.items():
            query = query.where(
                or_(
                    Content.title.ilike(f'%{keyword}%') * weight,
                    Content.text_content.ilike(f'%{keyword}%') * weight
                )
            )

    # Exclude Keywords
    if params.exclude_keywords:
        exclude_keywords_list = params.exclude_keywords.split(",")
        for keyword in exclude_keywords_list:
            query = query.where(
                and_(
                    ~Content.title.ilike(f'%{keyword}%'),
                    ~Content.text_content.ilike(f'%{keyword}%')
                )
            )

    return query


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


def merge_entities(filtered_entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged_entities = {}
    for entity in filtered_entities:
        name_key = entity['name'].lower()  # Use lowercase for comparison
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
    return sorted(merged_entities.values(), key=lambda x: x['relevance_score'], reverse=True)


# ----------------------------
# Route Handlers
# ----------------------------

##### Regular Articles Search
@router.get("/contents")
async def get_contents(
    params: ContentsQueryParams = Depends(),
    session: AsyncSession = Depends(get_session),
):
    try:
        async with session.begin():
            # Base query with eager loading
            query = select(Content).options(
                selectinload(Content.entities).selectinload(Entity.locations),
                selectinload(Content.tags),
                selectinload(Content.evaluation),
                selectinload(Content.media_details)
            )

            # Apply date filters
            query = apply_date_filters(query, params.from_date, params.to_date)

            # Apply search filters
            query = apply_search_filters(query, params.search_query, params.search_type)

            # Apply other common filters
            query = apply_common_filters(query, params)

            # Apply sorting
            if params.sort_by:
                sort_column = getattr(ContentEvaluation, params.sort_by, None)
                if sort_column:
                    if params.sort_order == "desc":
                        query = query.order_by(desc(sort_column))
                    else:
                        query = query.order_by(sort_column)

            # Execute query with pagination
            result = await session.execute(query.offset(params.skip).limit(params.limit))
            contents = result.unique().scalars().all()

            # Format response
            contents_data = [
                {
                    "id": str(content.id),
                    "url": content.url,
                    "title": content.title,
                    "source": content.source,
                    "insertion_date": content.insertion_date,
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
                                    "coordinates": loc.coordinates.tolist() if loc.coordinates else None
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
                for content in contents
            ]

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
    entities = []  # Initialize entities to avoid UnboundLocalError
    try:
        # Subquery to find articles related to the given location
        subquery = (
            select(Content.id)
            .join(ContentEntity, Content.id == ContentEntity.content_id)
            .join(Entity, ContentEntity.entity_id == Entity.id)
            .join(EntityLocation, Entity.id == EntityLocation.entity_id)
            .join(Location, EntityLocation.location_id == Location.id)
            .where(Location.name == location_name)
        ).subquery()  # Ensure subquery is correctly defined

        # Main query to get all entities from the articles related to the location
        query = (
            select(
                Entity.name,
                Entity.entity_type,
                func.count(distinct(Content.id)).label('article_count'),
                func.sum(ContentEntity.frequency).label('total_frequency')
            )
            .join(ContentEntity, Entity.id == ContentEntity.entity_id)
            .join(Content, ContentEntity.content_id == Content.id)
            .where(Content.id.in_(select(subquery)))
            .group_by(Entity.id, Entity.name, Entity.entity_type)
        )

        result = await session.execute(query)
        entities = result.all()

        logger.info(f"Query for location '{location_name}' returned {len(entities)} entities")

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
        merged_entities = merge_entities(filtered_entities)

        # Paginate
        paginated_entities = merged_entities[skip:skip+limit]

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
            if e.entity_type == 'PERSON':
                relevance_score *= 1.75

            filtered_entities.append({
                "name": cleaned_name,
                "type": e.entity_type,
                "article_count": e.article_count,
                "total_frequency": e.total_frequency,
                "relevance_score": relevance_score
            })

        # Merge similar entities
        merged_entities = merge_entities(filtered_entities)

        # Paginate
        paginated_entities = merged_entities[request.skip:request.skip+request.limit]

        logger.info(f"Returning {len(paginated_entities)} most relevant entities for given articles")

        return paginated_entities

    except Exception as e:
        logger.error(f"Error in get_most_relevant_entities: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


#### Articles By Entity
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

        contents_data = [
            {
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
                                "coordinates": loc.coordinates.tolist() if loc.coordinates else None
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
            for content in contents
        ]

        logger.info(f"Returning {len(contents_data)} articles for entity '{entity_name}'")
        return contents_data

    except Exception as e:
        logger.error(f"Error retrieving articles for entity '{entity_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving articles")


#### Articles By Location
@router.get("/contents_by_location/{location}")
async def get_articles_by_location(
    location: str,
    skip: int = 0,
    limit: int = 10,
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
            contents_data = [
                {
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
                                    "coordinates": loc.coordinates.tolist() if loc.coordinates else None
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
                for content in contents
            ]

            # Reverse the list before returning
            contents_data.reverse()
            return contents_data

    except Exception as e:
        logger.error(f"Error retrieving articles for location '{location}': {e}")
        raise HTTPException(status_code=500, detail="Error retrieving articles")


@router.get("/time_series_entity_in_dimensions", response_model=None)
async def get_entity_time_relevance(
    entity: str,
    timeframe_from: str,
    timeframe_to: str,
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    try:
        # Convert string dates to datetime objects
        timeframe_from_dt = datetime.strptime(timeframe_from, '%Y-%m-%d')
        timeframe_to_dt = datetime.strptime(timeframe_to, '%Y-%m-%d')

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
                Content.insertion_date.between(timeframe_from_dt, timeframe_to_dt)
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
        truncated_date = func.date_trunc('day', func.cast(Content.insertion_date, datetime)).label('date')

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
                func.cast(Content.insertion_date, datetime).between(timeframe_from, timeframe_to)
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


@router.get("/top_entities_by_score")
async def top_entities_by_score(
    request: TopEntitiesByScoreRequest,
    session: AsyncSession = Depends(get_session)
) -> List[Dict[str, Any]]:
    try:
        # Validate score_type
        valid_scores = {
            'sociocultural_interest',
            'global_political_impact',
            'regional_political_impact',
            'global_economic_impact',
            'regional_economic_impact'
        }

        if request.score_type not in valid_scores:
            logger.error(f"Invalid score type: {request.score_type}")
            raise HTTPException(status_code=400, detail=f"Invalid score type: {request.score_type}")

        # Convert string dates to datetime objects
        timeframe_from = datetime.strptime(request.timeframe_from, '%Y-%m-%d')
        timeframe_to = datetime.strptime(request.timeframe_to, '%Y-%m-%d')

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
            .limit(request.limit)
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

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error in top_entities_by_score: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/related_entities/{entity_name}")
async def get_related_entities(
    entity_name: str,
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session)
):
    """
    Retrieve entities that are most frequently associated with the given entity.
    """
    entities = []  # Initialize entities to avoid UnboundLocalError
    try:
        # Subquery to find articles related to the given entity
        subquery = (
            select(Content.id)
            .join(ContentEntity, Content.id == ContentEntity.content_id)
            .join(Entity, ContentEntity.entity_id == Entity.id)
            .where(Entity.name == entity_name)
        ).subquery()

        # Main query to get all entities from the related articles, excluding the original entity
        query = (
            select(
                Entity.name,
                Entity.entity_type,
                func.count(distinct(Content.id)).label('article_count'),
                func.sum(ContentEntity.frequency).label('total_frequency')
            )
            .join(ContentEntity, Entity.id == ContentEntity.entity_id)
            .join(Content, ContentEntity.content_id == Content.id)
            .where(Content.id.in_(select(subquery)))
            .where(Entity.name != entity_name)  # Exclude the original entity
            .group_by(Entity.id, Entity.name, Entity.entity_type)
        )

        result = await session.execute(query)
        entities = result.all()

        logger.info(f"Query for entity '{entity_name}' returned {len(entities)} related entities")

        # Filter and calculate relevance score
        filtered_entities = []
        for e in entities:
            # Clean the name by removing possessives but maintain capitalization
            cleaned_name = e.name.replace("'s", "").replace("'ss", "")
            comparison_name = cleaned_name.lower()

            if comparison_name != entity_name.lower():
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
        merged_entities = merge_entities(filtered_entities)

        # Paginate
        paginated_entities = merged_entities[skip:skip+limit]

        logger.info(f"Returning {len(paginated_entities)} merged related entities for '{entity_name}'")

        return paginated_entities

    except Exception as e:
        logger.error(f"Error in get_related_entities: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")
    finally:
        if not entities:
            # Check if the entity exists
            entity_check = await session.execute(select(Entity).where(Entity.name == entity_name))
            entity = entity_check.scalar_one_or_none()
            if entity:
                logger.info(f"Entity '{entity_name}' exists in the database but no related entities found")
            else:
                logger.warning(f"Entity '{entity_name}' does not exist in the database")