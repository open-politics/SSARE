import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, Query, APIRouter
from sqlmodel import select
from contextlib import asynccontextmanager
import httpx

from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pgvector.sqlalchemy import Vector
from sqlalchemy import and_, func, or_
from sqlalchemy import inspect
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.adb import get_session
from core.models import Article, Entity, Location, NewsArticleClassification
from core.service_mapping import config
from .models import SearchType

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


router = APIRouter()

##### Regular Articles Search
@router.get("/articles")
async def get_articles(
    url: Optional[str] = None,
    search_query: Optional[str] = None,
    search_type: SearchType = SearchType.TEXT,
    has_embeddings: Optional[bool] = Query(None, description="Filter articles with embeddings"),
    has_geocoding: Optional[bool] = Query(None, description="Filter articles with geocoding"),
    has_entities: Optional[bool] = Query(None, description="Filter articles with entities"),
    has_classification: Optional[bool] = Query(None, description="Filter articles with classification"),
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
                f"has_embeddings={has_embeddings}, has_geocoding={has_geocoding}, has_entities={has_entities}, "
                f"has_classification={has_classification}, skip={skip}, limit={limit}, "
                f"sort_by={sort_by}, sort_order={sort_order}, filters={filters}, "
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
            count_query = select(func.count()).select_from(Article)
            total_count = await session.execute(count_query)
            total_count = total_count.scalar()
            logger.info(f"Total number of articles in the database: {total_count}")

            # Modify the initial query to include a join with NewsArticleClassification
            query = select(Article).options(
                selectinload(Article.entities).selectinload(Entity.locations),
                selectinload(Article.tags),
                selectinload(Article.classification)
            ).join(NewsArticleClassification, isouter=True)  # Use outer join in case some articles don't have classification
            
            logger.info(f"Initial query: {query}")

            # Apply basic filters
            if url:
                query = query.where(Article.url == url)
            if has_geocoding:
                query = query.where(Article.entities.any(Entity.locations.any()))
            if has_embeddings is not None:
                query = query.where(Article.embeddings != None if has_embeddings else Article.embeddings == None)
            if has_entities is not None:
                query = query.where(Article.entities.any() if has_entities else ~Article.entities.any())
            if has_classification is not None:
                query = query.where(Article.classification != None if has_classification else Article.classification == None)

            logger.info(f"Query after basic filters: {query}")

            if news_category or secondary_category or keyword:
                category_conditions = []
                if news_category:
                    category_conditions.append(NewsArticleClassification.news_category == news_category)
                if secondary_category:
                    category_conditions.append(NewsArticleClassification.secondary_categories.any(secondary_category))
                if keyword:
                    category_conditions.append(NewsArticleClassification.keywords.any(keyword))
                
                if category_conditions:
                    query = query.where(or_(*category_conditions))

            # Apply search based on search_type
            if search_query:
                if search_type == SearchType.TEXT:
                    search_condition = or_(
                        Article.headline.ilike(f'%{search_query}%'), 
                        Article.paragraphs.ilike(f'%{search_query}%')
                    )
                    query = query.where(search_condition)
                    logger.info(f"Applied text search condition: {search_condition}")
                    
                    # Log the count of articles that match the search condition
                    count_query = select(func.count()).select_from(Article).where(search_condition)
                    search_count = await session.execute(count_query)
                    search_count = search_count.scalar()
                    logger.info(f"Number of articles matching the search query: {search_count}")
                elif search_type == SearchType.SEMANTIC and has_embeddings != False:
                    try:
                        # Get query embedding from NLP service
                        async with httpx.AsyncClient() as client:
                            response = await client.get(f"{config.service_urls['embedding_service']}/generate_query_embeddings", params={"query": search_query})
                            response.raise_for_status()
                            query_embeddings = response.json()["embeddings"]

                        embedding_array = query_embeddings
                        query = query.order_by(Article.embeddings.l2_distance(embedding_array)).limit(limit)
                    except httpx.HTTPError as e:
                        logger.error(f"Error calling NLP service: {e}")
                        raise HTTPException(status_code=500, detail="Failed to generate query embedding")
                    except Exception as e:
                        logger.error(f"Unexpected error in semantic search: {e}")
                        raise HTTPException(status_code=500, detail="Unexpected error in semantic search")

            logger.info(f"Query after search: {query}")

            # Apply entity filters
            if entity_list:
                query = query.join(Article.entities).where(Entity.name.in_(entity_list))

            # Apply location filters
            if location_list:
                query = query.join(Article.entities).join(Entity.locations).where(Location.name.in_(location_list))

            # Apply topic filters
            if topic_list:
                query = query.where(NewsArticleClassification.secondary_categories.any(topic_list))

            # Apply classification score filters
            for score_type, score_range in score_filters.items():
                min_score, max_score = score_range
                query = query.where(
                    and_(
                        getattr(NewsArticleClassification, score_type) >= min_score,
                        getattr(NewsArticleClassification, score_type) <= max_score
                    )
                )

            # Apply keyword weights
            if keyword_weights_dict:
                for keyword, weight in keyword_weights_dict.items():
                    query = query.where(
                        or_(
                            Article.headline.ilike(f'%{keyword}%') * weight,
                            Article.paragraphs.ilike(f'%{keyword}%') * weight
                        )
                    )

            # Apply exclusion keywords
            if exclude_keywords_list:
                for keyword in exclude_keywords_list:
                    query = query.where(
                        and_(
                            ~Article.headline.ilike(f'%{keyword}%'),
                            ~Article.paragraphs.ilike(f'%{keyword}%')
                        )
                    )

            # Dynamically apply filters based on NewsArticleClassification fields
            if filter_dict:
                classification_fields = inspect(NewsArticleClassification).c.keys()
                for field, value in filter_dict.items():
                    if field in classification_fields:
                        if isinstance(value, dict) and 'min' in value and 'max' in value:
                            query = query.where(and_(
                                getattr(NewsArticleClassification, field) >= value['min'],
                                getattr(NewsArticleClassification, field) <= value['max']
                            ))
                        else:
                            query = query.where(getattr(NewsArticleClassification, field) == value)

            # Apply sorting
            if sort_by:
                sort_column = getattr(NewsArticleClassification, sort_by, None)
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
            articles = result.unique().all()

            logger.info(f"Number of articles returned: {len(articles)}")

            articles_data = []
            for article_tuple in articles:
                article = article_tuple[0]  # The Article object is the first item in the tuple
                article_dict = {
                    "id": str(article.id),
                    "url": article.url,
                    "headline": article.headline,
                    "source": article.source,
                    "insertion_date": article.insertion_date.isoformat() if article.insertion_date else None,
                    "paragraphs": article.paragraphs,
                    "embeddings": article.embeddings.tolist() if article.embeddings is not None else None,
                    "entities": [
                        {
                            "id": str(e.id),
                            "name": e.name,
                            "entity_type": e.entity_type,
                            "locations": [
                                {
                                    "name": loc.name,
                                    "type": loc.type,
                                    "coordinates": loc.coordinates.tolist() if loc.coordinates is not None else None
                                } for loc in e.locations
                            ] if e.locations else []
                        } for e in article.entities
                    ] if article.entities else [],
                    "tags": [
                        {
                            "id": str(t.id),
                            "name": t.name
                        } for t in (article.tags or [])
                    ],
                    "classification": article.classification.dict() if article.classification else None
                }
                articles_data.append(article_dict)

            logger.info(f"Returning {len(articles_data)} articles")
            return articles_data

    except ValueError as e:
        logger.error(f"Invalid value for skip or limit: {e}")
        raise HTTPException(status_code=400, detail="Invalid value for skip or limit")
    except Exception as e:
        logger.error(f"Error retrieving articles: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving articles")

###### Entities for Location
@router.get("/location_entities/{location_name}")
async def get_location_entities(
    location_name: str, 
    skip: int = 0, 
    limit: int = 50, 
    session: AsyncSession = Depends(get_session)
    ):
    try:
        # Subquery to find articles related to the given location
        subquery = (
            select(Article.id)
            .join(ArticleEntity, Article.id == ArticleEntity.article_id)
            .join(Entity, ArticleEntity.entity_id == Entity.id)
            .join(EntityLocation, Entity.id == EntityLocation.entity_id)
            .join(Location, EntityLocation.location_id == Location.id)
            .where(Location.name == location_name)
            .distinct()
            .subquery()
        )

        # Main query to get all entities from the articles related to the location
        query = (
            select(
                Entity.name,
                Entity.entity_type,
                func.count(distinct(Article.id)).label('article_count'),
                func.sum(ArticleEntity.frequency).label('total_frequency')
            )
            .join(ArticleEntity, Entity.id == ArticleEntity.entity_id)
            .join(Article, ArticleEntity.article_id == Article.id)
            .where(Article.id.in_(subquery))
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

        # Sort by relevance score and apply pagination
        sorted_entities = sorted(filtered_entities, key=lambda x: x['relevance_score'], reverse=True)
        paginated_entities = sorted_entities[skip:skip+limit]

        logger.info(f"Query for location '{location_name}' returned {len(paginated_entities)} entities")

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
    

#### Articles By Entitiy
@router.get("/articles_by_entity/{entity_name}")
async def get_articles_by_entity(
    entity_name: str,
    skip: int = 0,
    limit: int = 10,
    session: AsyncSession = Depends(get_session)
    ):
    try:
        # Subquery to find articles related to the given entity
        subquery = (
            select(Article.id)
            .join(ArticleEntity, Article.id == ArticleEntity.article_id)
            .join(Entity, ArticleEntity.entity_id == Entity.id)
            .where(Entity.name == entity_name)
            .distinct()
            .subquery()
        )

        # Main query to get articles related to the entity
        query = (
            select(Article)
            .where(Article.id.in_(subquery))
            .offset(skip)
            .limit(limit)
        )

        result = await session.execute(query)
        articles = result.scalars().all()

        articles_data = []
        for article in articles:
            article_dict = {
                "id": str(article.id),
                "url": article.url,
                "headline": article.headline,
                "source": article.source,
                "insertion_date": article.insertion_date.isoformat() if article.insertion_date else None,
                "paragraphs": article.paragraphs,
                "embeddings": article.embeddings.tolist() if article.embeddings is not None else None,
                "entities": [
                    {
                        "id": str(e.id),
                        "name": e.name,
                        "entity_type": e.entity_type,
                        "locations": [
                            {
                                "name": loc.name,
                                "type": loc.type,
                                "coordinates": loc.coordinates.tolist() if loc.coordinates is not None else None
                            } for loc in e.locations
                        ] if e.locations else []
                    } for e in article.entities
                ] if article.entities else [],
                "tags": [
                    {
                        "id": str(t.id),
                        "name": t.name
                    } for t in (article.tags or [])
                ],
                "classification": article.classification.dict() if article.classification else None
            }
            articles_data.append(article_dict)

        logger.info(f"Returning {len(articles_data)} articles for entity '{entity_name}'")
        return articles_data

    except Exception as e:
        logger.error(f"Error retrieving articles for entity '{entity_name}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving articles")