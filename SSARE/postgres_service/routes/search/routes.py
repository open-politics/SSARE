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
from sqlalchemy import and_, func, or_, desc, distinct
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.adb import get_session
from core.models import Content, Entity, Location, ContentClassification, ContentEntity, ContentChunk, EntityLocation
from core.service_mapping import config
from .models import SearchType
from core.utils import logger

from pydantic import BaseModel
import uuid


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
    entities: Optional[str] = Query(None, description="Comma-separated list of entities"),
    locations: Optional[str] = Query(None, description="Comma-separated list of locations"),
    topics: Optional[str] = Query(None, description="Comma-separated list of topics"),
    classification_scores: Optional[str] = Query(None, description="JSON string of classification score ranges"),
    keyword_weights: Optional[str] = Query(None, description="JSON string of keyword weights"),
    exclude_keywords: Optional[str] = Query(None, description="Comma-separated list of exclude keywords"),
    ):
    logger.info(f"Received parameters: url={url}, search_query={search_query}, search_type={search_type}, "
                f"skip={skip}, limit={limit}, sort_by={sort_by}, sort_order={sort_order}, filters={filters}, "
                f"entities={entities}, locations={locations}, topics={topics}, classification_scores={classification_scores}, "
                f"keyword_weights={keyword_weights}, exclude_keywords={exclude_keywords}")

    try:
        # Parse filters
        filter_dict = json.loads(filters) if filters else {}
        entity_list = entities.split(",") if entities else []
        location_list = locations.split(",") if locations else []
        topic_list = topics.split(",") if topics else []
        score_filters = json.loads(classification_scores) if classification_scores else {}
        keyword_weights_dict = json.loads(keyword_weights) if keyword_weights else {}
        exclude_keywords_list = exclude_keywords.split(",") if exclude_keywords else []

        # Ensure skip is an integer
        skip = int(skip) if skip is not None else 0

        async with session.begin():
            # First, let's check if there are any articles in the database
            count_query = select(func.count()).select_from(Content)
            total_count = await session.execute(count_query)
            total_count = total_count.scalar()
            logger.info(f"Total number of articles in the database: {total_count}")

            # Modify the initial query to include a join with ContentChunk
            query = select(Content).options(
                selectinload(Content.entities).selectinload(Entity.locations),
                selectinload(Content.tags),
                selectinload(Content.classification)
            ).join(ContentChunk, Content.id == ContentChunk.content_id, isouter=True)
            
            logger.info(f"Initial query: {query}")

            # Apply basic filters
            if url:
                query = query.where(Content.url == url)
            

            logger.info(f"Query after basic filters: {query}")

            if news_category or secondary_category or keyword:
                category_conditions = []
                if news_category:
                    category_conditions.append(ContentClassification.news_category == news_category)
                if secondary_category:
                    category_conditions.append(ContentClassification.secondary_categories.any(secondary_category))
                if keyword:
                    category_conditions.append(ContentClassification.keywords.any(keyword))
                
                if category_conditions:
                    query = query.where(or_(*category_conditions))

            # Apply search based on search_type
            if search_query:
                if search_type == SearchType.TEXT:
                    search_condition = or_(
                        Content.title.ilike(f'%{search_query}%'), 
                        Content.text_content.ilike(f'%{search_query}%')
                    )
                    query = query.where(search_condition)
                    logger.info(f"Applied text search condition: {search_condition}")
                    
                    # Log the count of articles that match the search condition
                    count_query = select(func.count()).select_from(Content).where(search_condition)
                    search_count = await session.execute(count_query)
                    search_count = search_count.scalar()
                    logger.info(f"Number of articles matching the search query: {search_count}")
                elif search_type == SearchType.SEMANTIC:
                    try:
                        # Get query embedding from NLP service
                        async with httpx.AsyncClient() as client:
                            response = await client.get(f"{config.service_urls['embedding_service']}/generate_query_embeddings", params={"query": search_query})
                            response.raise_for_status()
                            query_embeddings = response.json()["embeddings"]

                        embedding_array = query_embeddings

                        # Use ContentChunk embeddings for initial retrieval
                        query = query.order_by(ContentChunk.embeddings.l2_distance(embedding_array)).limit(limit)
                    except httpx.HTTPError as e:
                        logger.error(f"Error calling NLP service: {e}")
                        raise HTTPException(status_code=500, detail="Failed to generate query embedding")
                    except Exception as e:
                        logger.error(f"Unexpected error in semantic search: {e}")
                        raise HTTPException(status_code=500, detail="Unexpected error in semantic search")

            logger.info(f"Query after search: {query}")

            # Apply entity filters
            if entity_list:
                query = query.join(Content.entities).where(Entity.name.in_(entity_list))

            # Apply location filters
            if location_list:
                query = query.join(Content.entities).join(Entity.locations).where(Location.name.in_(location_list))

            # Apply topic filters
            if topic_list:
                query = query.where(ContentClassification.secondary_categories.any(topic_list))

            # Apply classification score filters
            for score_type, score_range in score_filters.items():
                min_score, max_score = score_range
                query = query.where(
                    and_(
                        getattr(ContentClassification, score_type) >= min_score,
                        getattr(ContentClassification, score_type) <= max_score
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

            # Dynamically apply filters based on ContentClassification fields
            if filter_dict:
                classification_fields = inspect(ContentClassification).c.keys()
                for field, value in filter_dict.items():
                    if field in classification_fields:
                        if isinstance(value, dict) and 'min' in value and 'max' in value:
                            query = query.where(and_(
                                getattr(ContentClassification, field) >= value['min'],
                                getattr(ContentClassification, field) <= value['max']
                            ))
                        else:
                            query = query.where(getattr(ContentClassification, field) == value)

            # Apply sorting
            if sort_by:
                sort_column = getattr(ContentClassification, sort_by, None)
                if sort_column:
                    query = query.order_by(desc(sort_column) if sort_order == "desc" else sort_column)

            # After applying all filters
            count_query = select(func.count()).select_from(query.subquery())
            filtered_count = await session.execute(count_query)
            filtered_count = filtered_count.scalar()
            logger.info(f"Number of articles after applying all filters: {filtered_count}")

            # Log the final SQL query
            logger.info(f"Final SQL query: {query.compile(compile_kwargs={'literal_binds': True})}")

            # Execute query
            result = await session.execute(query.offset(skip).limit(limit))
            contents = result.unique().all()

            # Rerank articles based on some criteria if necessary
            # For example, you could rerank based on the average similarity of chunks

            logger.info(f"Number of contents returned: {len(contents)}")

            contents_data = []
            for content_tuple in contents:
                content = content_tuple[0]  # The Content object is the first item in the tuple
                content_dict = {
                    "id": str(content.id),
                    "url": content.url,
                    "title": content.title,
                    "source": content.source,
                    "insertion_date": content.insertion_date if content.insertion_date else None,
                    "text_content": content.text_content,
                    "embeddings": content.embeddings.tolist() if content.embeddings is not None else None,
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
                    "classification": content.classification.dict() if content.classification else None
                }
                contents_data.append(content_dict)

            logger.info(f"Returning {len(contents_data)} contents")
            return contents_data

    except ValueError as e:
        logger.error(f"Invalid value for skip or limit: {e}")
        raise HTTPException(status_code=400, detail="Invalid value for skip or limit")
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
            .distinct()
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
            .where(Content.id.in_(select(subquery)))  # Explicitly convert subquery to select()
            .group_by(Entity.id, Entity.name, Entity.entity_type)
        )

        result = await session.execute(query)
        entities = result.all()

        # Filter and calculate relevance score
        filtered_entities = []
        for e in entities:
            if e.name.lower() != location_name.lower():
                # Adjust relevance score calculation
                relevance_score = (e.total_frequency * math.log(e.article_count + 1))
                
                # Boost score for PERSON entities
                if e.entity_type == 'PERSON':
                    relevance_score *= 1.75
                
                filtered_entities.append({
                    "name": e.name,
                    "type": e.entity_type,
                    "article_count": e.article_count,
                    "total_frequency": e.total_frequency,
                    "relevance_score": relevance_score
                })

        # Merge similar entities
        merged_entities = {}
        for entity in filtered_entities:
            name = entity['name'].lower()
            found = False
            for key in merged_entities:
                if name in key or key in name:
                    # Merge the entities
                    merged_entities[key]['article_count'] += entity['article_count']
                    merged_entities[key]['total_frequency'] += entity['total_frequency']
                    merged_entities[key]['relevance_score'] += entity['relevance_score']
                    # Keep the longer name
                    if len(entity['name']) > len(merged_entities[key]['name']):
                        merged_entities[key]['name'] = entity['name']
                    found = True
                    break
            if not found:
                merged_entities[name] = entity

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
            relevance_score = (e.total_frequency * math.log(e.article_count + 1))
            if e.entity_type == 'PERSON':
                relevance_score *= 1.75

            filtered_entities.append({
                "name": e.name,
                "type": e.entity_type,
                "article_count": e.article_count,
                "total_frequency": e.total_frequency,
                "relevance_score": relevance_score
            })

        # Merge similar entities
        merged_entities = {}
        for entity in filtered_entities:
            name = entity['name'].lower()
            found = False
            for key in merged_entities:
                if name in key or key in name:
                    merged_entities[key]['article_count'] += entity['article_count']
                    merged_entities[key]['total_frequency'] += entity['total_frequency']
                    merged_entities[key]['relevance_score'] += entity['relevance_score']
                    if len(entity['name']) > len(merged_entities[key]['name']):
                        merged_entities[key]['name'] = entity['name']
                    found = True
                    break
            if not found:
                merged_entities[name] = entity

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
        # Subquery to find articles related to the given entity
        subquery = (
            select(Content.id)
            .join(ContentEntity, Content.id == ContentEntity.content_id)
            .join(Entity, ContentEntity.entity_id == Entity.id)
            .where(Entity.name == entity_name)
            .distinct()
            .subquery()
        )

        # Main query to get articles related to the entity
        query = (
            select(Content)
            .where(Content.id.in_(subquery))
            .offset(skip)
            .limit(limit)
        )

        result = await session.execute(query)
        contents = result.scalars().all()

        contents_data = []
        for content in contents:
            content_dict = {
                "id": str(content.id),
                "url": content.url,
                "title": content.title,
                "source": content.source,
                "insertion_date": content.insertion_date.isoformat() if content.insertion_date else None,
                "text_content": content.text_content,
                "embeddings": content.embeddings.tolist() if content.embeddings is not None else None,
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
                "classification": content.classification.dict() if content.classification else None
            }
            contents_data.append(content_dict)

        logger.info(f"Returning {len(contents_data)} articles for entity '{entity_name}'")
        return contents_data

    except Exception as e:
        logger.error(f"Error retrieving articles for entity '{entity_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving articles")



