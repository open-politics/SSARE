import os
import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from sqlmodel import SQLModel, Field, create_engine, Session, select, update
from sqlmodel import Column, JSON
from contextlib import asynccontextmanager
from enum import Enum
import httpx
import math
import pandas as pd
import uuid
from io import StringIO

from fastapi import Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from sqlalchemy import and_, delete, func, insert, or_, text, update
from sqlalchemy import inspect
from sqlalchemy import desc
from sqlalchemy import join
from sqlalchemy import alias, distinct
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session
from typing import AsyncGenerator

from core.adb import engine, get_session, create_db_and_tables
from core.middleware import add_cors_middleware
from core.models import Article, Articles, ArticleEntity, ArticleTag, Entity, EntityLocation, Location, Tag, NewsArticleClassification
from core.service_mapping import config


########################################################################################
## SETUP

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis connection
redis_conn_flags = Redis(host='redis', port=config.REDIS_PORT, db=0)  # For flags


async def lifespan(app):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
add_cors_middleware(app)


@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}, 200

class SearchType(str, Enum):
    TEXT = "text"
    SEMANTIC = "semantic"
    STRUCTURED = "structured"

import os
import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from sqlmodel import SQLModel, Field, create_engine, Session, select, update
from sqlmodel import Column, JSON
from contextlib import asynccontextmanager
from enum import Enum
import httpx
import math
import pandas as pd
import uuid
from io import StringIO

from fastapi import Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from sqlalchemy import and_, delete, func, insert, or_, text, update
from sqlalchemy import inspect
from sqlalchemy import desc
from sqlalchemy import join
from sqlalchemy import alias, distinct
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session
from typing import AsyncGenerator

from core.adb import engine, get_session, create_db_and_tables
from core.middleware import add_cors_middleware
from core.models import Article, Articles, ArticleEntity, ArticleTag, Entity, EntityLocation, Location, Tag, NewsArticleClassification
from core.service_mapping import config

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis connection
redis_conn_flags = Redis(host='redis', port=config.REDIS_PORT, db=0)  # For flags

async def lifespan(app):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
add_cors_middleware(app)

@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}, 200

class SearchType(str, Enum):
    TEXT = "text"
    SEMANTIC = "semantic"
    STRUCTURED = "structured"

@app.get("/articles")
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
    keyword_weights: Optional[str] = Query(None, description="JSON string of keyword weights"),  # New parameter for keyword weights
    exclude_keywords: Optional[str] = Query(None, description="Comma-separated list of exclude keywords"),  # New parameter for exclude keywords
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
        

@app.get("/classification_fields")
async def get_classification_fields():
    fields = inspect(NewsArticleClassification).c
    return {name: str(field.type) for name, field in fields.items()}
        

###### ENTITIES SECTION
@app.get("/location_entities/{location_name}")
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
            
@app.get("/articles_by_entity/{entity_name}")
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
########################################################################################
## HELPER FUNCTIONS

@app.post("/deduplicate_articles")
async def deduplicate_articles(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article).group_by(Article.id, Article.url).having(func.count() > 1)
            result = await session.execute(query)
            duplicate_articles = result.scalars().all()

        for article in duplicate_articles:
            logger.info(f"Duplicate article: {article.url}")
            await session.delete(article)

        await session.commit()
        return {"message": "Duplicate articles deleted successfully."}
    except Exception as e:
        logger.error(f"Error deduplicating articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

########################################################################################
## 1. SCRAPING PIPELINE

# Produce Flags for scraping
@app.get("/flags")
async def produce_flags():
    await redis_conn_flags.delete("scrape_sources")
    flags = ["cnn", "bbc", "dw", "pynews"]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@app.post("/store_raw_articles")
async def store_raw_articles(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=1, decode_responses=True)
        raw_articles = await redis_conn.lrange('raw_articles_queue', 0, -1)
        articles = [json.loads(article) for article in raw_articles]
        articles = Articles(articles=[Article(**{k: str(v) if not pd.isna(v) else '' for k, v in article.items()}) for article in articles])
        logger.info("Retrieved raw articles from Redis")
        logger.info(f"First 3 articles: {[{k: v for k, v in article.dict().items() if k in ['url', 'headline']} for article in articles.articles[:3]]}")

        async with session.begin():
            for article in articles.articles:
                try:
                    existing_article = await session.execute(select(Article).where(Article.url == article.url))
                    if existing_article.scalar_one_or_none() is not None:
                        logger.info(f"Updating existing article: {article.url}")
                        await session.execute(update(Article).where(Article.url == article.url).values(**article.dict(exclude_unset=True)))
                    else:
                        logger.info(f"Adding new article: {article.url}")
                        session.add(article)
                    await session.flush()
                except Exception as e:
                    logger.error(f"Error processing article {article.url}: {str(e)}")
                    # Continue processing other articles

        await session.commit()

        await redis_conn.ltrim('raw_articles_queue', len(raw_articles), -1)

        await redis_conn.close()
        return {"message": "Raw articles processed successfully."}
    except Exception as e:
        logger.error(f"Error processing articles: {e}")
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await session.close()

########################################################################################
## 2. EMBEDDING PIPELINE

@app.post("/create_embedding_jobs")
async def create_embedding_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Trying to create embedding jobs.")
    try:
        async with session.begin():
            query = select(Article).where(Article.embeddings == None)
            result = await session.execute(query)
            articles_without_embeddings = result.scalars().all()
            logger.info(f"Found {len(articles_without_embeddings)} articles without embeddings.")

            redis_conn_unprocessed_articles = await Redis(host='redis', port=config.REDIS_PORT, db=5)
            
            # Get existing articles in the queue
            existing_urls = set(await redis_conn_unprocessed_articles.lrange('articles_without_embedding_queue', 0, -1))
            existing_urls = {json.loads(url.decode('utf-8'))['url'] for url in existing_urls}

            articles_list = []
            not_pushed_count = 0
            for article in articles_without_embeddings:
                if article.url not in existing_urls:
                    articles_list.append(json.dumps({
                        'url': article.url,
                        'headline': article.headline,
                        'paragraphs': article.paragraphs
                    }))
                else:
                    not_pushed_count += 1

            logger.info(f"{not_pushed_count} articles already in queue, not pushed again.")

        if articles_list:
            await redis_conn_unprocessed_articles.rpush('articles_without_embedding_queue', *articles_list)
            logger.info(f"Pushed {len(articles_list)} articles to Redis queue.")
        else:
            logger.info("No new articles found that need embeddings.")

        await redis_conn_unprocessed_articles.close()
        return {"message": f"Embedding jobs created for {len(articles_list)} articles."}
    except Exception as e:
        logger.error(f"Failed to create embedding jobs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/store_articles_with_embeddings")
async def store_articles_with_embeddings(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=6)
        articles_with_embeddings = await redis_conn.lrange('articles_with_embeddings', 0, -1)

        async with session.begin():
            for article_with_embeddings in articles_with_embeddings:
                try:
                    article_data = json.loads(article_with_embeddings)
                    logger.info(f"Storing article with embedding: {article_data['url']}")

                    existing_article = await session.execute(select(Article).where(Article.url == article_data['url']))
                    existing_article = existing_article.scalar_one_or_none()

                    if existing_article:
                        logger.info(f"Updating article with embedding: {article_data['url']}")
                        for key, value in article_data.items():
                            if key == 'embedding':
                                setattr(existing_article, 'embedding', value)
                            else:
                                setattr(existing_article, key, value)
                    else:
                        article = Article(**article_data)
                        session.add(article)

                except ValidationError as e:
                    logger.error(f"Validation error for article: {e}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error: {e}")

        await session.commit()
        await redis_conn.ltrim('articles_with_embeddings', len(articles_with_embeddings), -1)
        await redis_conn.close()
        return {"message": "Articles with embeddings stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing articles with embeddings: {e}")
        raise HTTPException(status_code=400, detail=str(e))

########################################################################################
## 3. ENTITY PIPELINE

@app.post("/create_entity_extraction_jobs")
async def create_entity_extraction_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create entity extraction jobs.")
    try:
        query = select(Article).where(Article.entities == None)
        result = await session.execute(query)
        _articles = result.scalars().all()

        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=2)

        # Get existing articles in the queue
        existing_urls = set(await redis_conn.lrange('articles_without_entities_queue', 0, -1))
        existing_urls = {json.loads(url.decode('utf-8'))['url'] for url in existing_urls}   
        
        articles_list = []
        not_pushed_count = 0
        for article in _articles:
            if article.url not in existing_urls:
                articles_list.append(json.dumps({
                    'url': article.url,
                    'headline': article.headline,
                    'paragraphs': article.paragraphs
                }))
            else:
                not_pushed_count += 1

        logger.info(f"{not_pushed_count} articles already in queue, not pushed again.")

        if articles_list:
            await redis_conn.rpush('articles_without_entities_queue', *articles_list)
            logger.info(f"Pushed {len(articles_list)} articles to Redis queue.")
        else:
            logger.info("No new articles found that need entities.")

        await redis_conn.close()  # Close the Redis connection

        logger.info(f"Entity extraction jobs for {len(_articles)} articles created.")
        return {"message": "Entity extraction jobs created successfully."}
    except Exception as e:
        logger.error(f"Error creating entity extraction jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/store_articles_with_entities")
async def store_articles_with_entities(session: AsyncSession = Depends(get_session)):
    try:
        logger.info("Starting store_articles_with_entities function")
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=2, decode_responses=True)
        logger.info(f"Connected to Redis on port {config.REDIS_PORT}, db 2")
        articles = await redis_conn.lrange('articles_with_entities_queue', 0, -1)
        logger.info(f"Retrieved {len(articles)} articles from Redis queue")
        
        async with session.begin():
            logger.info("Starting database session")
            for index, article_json in enumerate(articles, 1):
                try:
                    article_data = json.loads(article_json)
                    logger.info(f"Processing article {index}/{len(articles)}: {article_data['url']}")
                    
                    # Update article fields excluding entities and id
                    article_update = {k: v for k, v in article_data.items() if k not in ['entities', 'id']}
                    stmt = update(Article).where(Article.url == article_data['url']).values(**article_update)
                    await session.execute(stmt)
                    
                    # Handle entities separately
                    if 'entities' in article_data:
                        # Get the article id
                        result = await session.execute(select(Article.id).where(Article.url == article_data['url']))
                        article_id = result.scalar_one()
                        
                        # Delete existing ArticleEntity entries for this article
                        await session.execute(delete(ArticleEntity).where(ArticleEntity.article_id == article_id))
                        
                        for entity_data in article_data['entities']:
                            # Create or get entity
                            entity_stmt = select(Entity).where(Entity.name == entity_data['text'], Entity.entity_type == entity_data['tag'])
                            result = await session.execute(entity_stmt)
                            entity = result.scalar_one_or_none()
                            
                            if not entity:
                                entity = Entity(name=entity_data['text'], entity_type=entity_data['tag'])
                                session.add(entity)
                                await session.flush()  # This will populate the id of the new entity
                            
                            # Create or update ArticleEntity link
                            article_entity_stmt = select(ArticleEntity).where(
                                ArticleEntity.article_id == article_id,
                                ArticleEntity.entity_id == entity.id
                            )
                            result = await session.execute(article_entity_stmt)
                            existing_article_entity = result.scalar_one_or_none()

                            if existing_article_entity:
                                existing_article_entity.frequency += 1
                            else:
                                article_entity = ArticleEntity(article_id=article_id, entity_id=entity.id)
                                session.add(article_entity)
                    
                except ValidationError as e:
                    logger.error(f"Validation error for article {article_data['url']}: {e}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error for article: {e}")

        logger.info("Changes committed to database")
        await redis_conn.ltrim('articles_with_entities_queue', len(articles), -1)
        logger.info("Redis queue trimmed")
        logger.info("Closing Redis connection")
        await redis_conn.close()
        logger.info("Articles with entities stored successfully")
        return {"message": "Articles with entities processed and stored successfully."}
    except Exception as e:
        logger.error(f"Error processing articles with entities: {e}")
        raise HTTPException(status_code=400, detail=str(e))

########################################################################################
## 4. GEOCODING PIPELINE

@app.post("/create_geocoding_jobs")
async def create_geocoding_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create geocoding jobs.")
    try:
        async with session.begin():
            # Select articles with entities that are locations and do not have geocoding
            query = select(Article).options(
                selectinload(Article.entities).selectinload(Entity.locations)
            ).where(
                Article.entities.any(
                    and_(
                        or_(Entity.entity_type == 'GPE', Entity.entity_type == 'LOC'),
                        ~Entity.locations.any(Location.coordinates != None)
                    )
                )
            )
            result = await session.execute(query)
            articles = result.scalars().all()
            logger.info(f"Found {len(articles)} articles with entities that need geocoding.")

            redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=3)

            # Get existing articles in the queue
            existing_urls = set(await redis_conn.lrange('articles_without_geocoding_queue', 0, -1))
            existing_urls = {json.loads(url.decode('utf-8'))['url'] for url in existing_urls}

            articles_list = []
            not_pushed_count = 0
            for article in articles:
                if article.url not in existing_urls:
                    gpe_entities = [entity for entity in article.entities if entity.entity_type in ('GPE', 'LOC') and not entity.locations]
                    
                    if gpe_entities:
                        article_dict = {
                            'url': article.url,
                            'headline': article.headline,
                            'paragraphs': article.paragraphs,
                            'entities': [{'name': entity.name, 'entity_type': entity.entity_type} for entity in gpe_entities]
                        }
                        articles_list.append(json.dumps(article_dict, ensure_ascii=False))
                        logger.info(f"Article {article.url} has {len(gpe_entities)} GPE or LOC entities that need geocoding.")
                else:
                    not_pushed_count += 1

            if articles_list:
                await redis_conn.rpush('articles_without_geocoding_queue', *articles_list)
                logger.info(f"Pushed {len(articles_list)} new articles to Redis queue for geocoding.")
            else:
                logger.info("No new articles found that need geocoding.")
            
            logger.info(f"{not_pushed_count} articles were not pushed to the queue as they were already present.")

            await redis_conn.close()
            return {"message": f"Geocoding jobs created for {len(articles_list)} new articles. {not_pushed_count} articles were already in the queue."}
    except Exception as e:
        logger.error(f"Error creating geocoding jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/store_articles_with_geocoding")
async def store_articles_with_geocoding(session: AsyncSession = Depends(get_session)):
    try:
        logger.info("Starting store_articles_with_geocoding function")
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4, decode_responses=True)
        logger.info(f"Connected to Redis on port {config.REDIS_PORT}, db 4")
        geocoded_articles = await redis_conn.lrange('articles_with_geocoding_queue', 0, -1)
        logger.info(f"Retrieved {len(geocoded_articles)} geocoded articles from Redis queue")
        
        for index, geocoded_article in enumerate(geocoded_articles, 1):
            try:
                geocoded_data = json.loads(geocoded_article)
                logger.info(f"Processing geocoded article {index}/{len(geocoded_articles)}: {geocoded_data['url']}")
                
                async with session.begin():
                    article = await session.execute(
                        select(Article).where(Article.url == geocoded_data['url'])
                    )
                    article = article.scalar_one_or_none()

                    if article:
                        for location_data in geocoded_data['geocoded_locations']:
                            entity = await session.execute(
                                select(Entity).where(Entity.name == location_data['name'], Entity.entity_type == "GPE")
                            )
                            entity = entity.scalar_one_or_none()
                            
                            if not entity:
                                entity = Entity(name=location_data['name'], entity_type="GPE")
                                session.add(entity)
                                await session.flush()  # Flush to get the entity ID
                            
                            location = await session.execute(
                                select(Location).where(Location.name == location_data['name'])
                            )
                            location = location.scalar_one_or_none()
                            
                            if not location:
                                location = Location(
                                    name=location_data['name'],
                                    type="GPE",
                                    coordinates=location_data['coordinates'],
                                    weight=location_data['weight']
                                )
                                session.add(location)
                                await session.flush()  # Flush to get the location ID
                            else:
                                # Update the weight if the new weight is higher
                                location.weight = max(location.weight, location_data['weight'])
                            
                            # Check if ArticleEntity already exists
                            existing_article_entity = await session.execute(
                                select(ArticleEntity).where(
                                    ArticleEntity.article_id == article.id,
                                    ArticleEntity.entity_id == entity.id
                                )
                            )
                            existing_article_entity = existing_article_entity.scalar_one_or_none()

                            if existing_article_entity:
                                # Update frequency if it already exists
                                await session.execute(
                                    update(ArticleEntity).
                                    where(ArticleEntity.article_id == article.id, ArticleEntity.entity_id == entity.id).
                                    values(frequency=ArticleEntity.frequency + 1)
                                )
                            else:
                                # Create new ArticleEntity if it doesn't exist
                                article_entity = ArticleEntity(article_id=article.id, entity_id=entity.id)
                                session.add(article_entity)

                            # Check if EntityLocation already exists
                            existing_entity_location = await session.execute(
                                select(EntityLocation).where(
                                    EntityLocation.entity_id == entity.id,
                                    EntityLocation.location_id == location.id
                                )
                            )
                            existing_entity_location = existing_entity_location.scalar_one_or_none()

                            if not existing_entity_location:
                                entity_location = EntityLocation(entity_id=entity.id, location_id=location.id)
                                session.add(entity_location)
                        
                        # Add the "geocoded" tag
                        tag = await session.execute(select(Tag).where(Tag.name == "geocoded"))
                        tag = tag.scalar_one_or_none()
                        if not tag:
                            tag = Tag(name="geocoded")
                            session.add(tag)
                            await session.flush()  # Flush to get the tag ID
                        
                        # Check if ArticleTag already exists
                        existing_article_tag = await session.execute(
                            select(ArticleTag).where(
                                ArticleTag.article_id == article.id,
                                ArticleTag.tag_id == tag.id
                            )
                        )
                        existing_article_tag = existing_article_tag.scalar_one_or_none()

                        if not existing_article_tag:
                            article_tag = ArticleTag(article_id=article.id, tag_id=tag.id)
                            session.add(article_tag)
                    else:
                        logger.error(f"Article not found: {geocoded_data['url']}")
                
            except Exception as e:
                logger.error(f"Error processing geocoded article {geocoded_data['url']}: {str(e)}")
                # Continue processing other articles

        await redis_conn.ltrim('articles_with_geocoding_queue', len(geocoded_articles), -1)
        logger.info("Cleared Redis queue")
        await redis_conn.close()
        logger.info("Closed Redis connection")
        return {"message": "Geocoded articles stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing geocoded articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))

########################################################################################
## 5. LLM CLASSIFICATION PIPELINE

@app.post("/create_classification_jobs")
async def create_classification_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create classification jobs.")
    try:
        async with session.begin():
            # Select articles with no tags
            query = select(Article).where(Article.classification == None)
            result = await session.execute(query)
            _articles = result.scalars().all()
            logger.info(f"Found {len(_articles)} articles with no classification.")

            redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4)
            existing_urls = set(await redis_conn.lrange('articles_without_classification_queue', 0, -1))
            existing_urls = {json.loads(url.decode('utf-8'))['url'] for url in existing_urls}

            articles_list = []
            not_pushed_count = 0
            for article in _articles:
                if article.url not in existing_urls:
                    articles_list.append(json.dumps({
                        'url': article.url,
                        'headline': article.headline,
                        'paragraphs': article.paragraphs,
                        'source': article.source
                    }))
                else:
                    not_pushed_count += 1
            
        if articles_list:
            await redis_conn.rpush('articles_without_classification_queue', *articles_list)
            logger.info(f"Pushed {len(articles_list)} articles to Redis queue for classification.")
        else:
            logger.info("No articles found that need classification.")
        await redis_conn.close()
        return {"message": f"Classification jobs created for {len(_articles)} articles."}
    except Exception as e:
        logger.error(f"Error creating classification jobs: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/store_articles_with_classification")
async def store_articles_with_classification(session: AsyncSession = Depends(get_session)):
    try:
        logger.info("Starting store_articles_with_classification function")
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4, decode_responses=True)
        logger.info(f"Connected to Redis on port {config.REDIS_PORT}, db 4")
        classified_articles = await redis_conn.lrange('articles_with_classification_queue', 0, -1)
        logger.info(f"Retrieved {len(classified_articles)} classified articles from Redis queue")
        
        async with session.begin():
            logger.info("Starting database session")
            for index, classified_article in enumerate(classified_articles, 1):
                try:
                    article_data = json.loads(classified_article)
                    logger.info(f"Processing article {index}/{len(classified_articles)}: {article_data['url']}")
                    
                    # Find the article by URL and eagerly load the classification
                    result = await session.execute(
                        select(Article).options(selectinload(Article.classification)).where(Article.url == article_data['url'])
                    )
                    article = result.scalar_one_or_none()

                    if article:
                        classification_data = article_data['classification']
                        if article.classification:
                            # Update existing classification
                            for key, value in classification_data.items():
                                setattr(article.classification, key, value)
                        else:
                            # Create new classification
                            article.classification = NewsArticleClassification(**classification_data)
                        
                        session.add(article)
                        logger.info(f"Updated article and classification: {article_data['url']}")
                    else:
                        logger.warning(f"Article not found in database: {article_data['url']}")

                except ValidationError as e:
                    logger.error(f"Validation error for article {article_data['url']}: {e}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error for article: {e}")

        await session.commit()
        logger.info("Changes committed to database")
        await redis_conn.ltrim('articles_with_classification_queue', len(classified_articles), -1)
        logger.info("Redis queue trimmed")
        await redis_conn.close()
        logger.info("Classified articles stored successfully")
        return {"message": "Classified articles stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing classified articles: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


#### MISC

@app.delete("/delete_all_classifications")
async def delete_all_classifications(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            # Delete all records from the NewsArticleClassification table
            await session.execute(delete(NewsArticleClassification))
            await session.commit()
            logger.info("All classifications deleted successfully.")
            return {"message": "All classifications deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting classifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting classifications")

@app.get("/articles_csv_quick")
async def get_articles_csv(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article)
            result = await session.execute(query)
            articles = result.scalars().all()

        # Convert articles to a list of dictionaries
        articles_data = [article.dict() for article in articles]

        # Create a DataFrame
        df = pd.DataFrame(articles_data)

        # Convert DataFrame to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=articles.csv"})

    except Exception as e:
        logger.error(f"Error generating CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating CSV")

@app.get("/articles_csv_full")
async def get_articles_csv(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article).options(
                selectinload(Article.entities).selectinload(Entity.locations),
                selectinload(Article.tags),
                selectinload(Article.classification)
            )
            result = await session.execute(query)
            articles = result.scalars().all()

        # Convert articles to a list of dictionaries
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

        # Flatten the data for CSV
        flattened_data = []
        for article in articles_data:
            base_data = {
                "id": article["id"],
                "url": article["url"],
                "headline": article["headline"],
                "source": article["source"],
                "insertion_date": article["insertion_date"],
                "paragraphs": article["paragraphs"],
                "embeddings": article["embeddings"],
            }
            if article["entities"]:
                for entity in article["entities"]:
                    entity_data = {
                        "entity_id": entity["id"],
                        "entity_name": entity["name"],
                        "entity_type": entity["entity_type"],
                        "locations": json.dumps(entity["locations"]),
                    }
                    flattened_data.append({**base_data, **entity_data})
            else:
                flattened_data.append(base_data)

        # Create a DataFrame
        df = pd.DataFrame(flattened_data)

        # Convert DataFrame to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=articles.csv"})

    except Exception as e:
        logger.error(f"Error generating CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating CSV")
