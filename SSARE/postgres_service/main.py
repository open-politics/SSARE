import os
import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from sqlmodel import SQLModel, Field, create_engine, Session, select, update
from sqlmodel import Column, JSON
from sqlalchemy import text
from pgvector.sqlalchemy import Vector
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from pydantic import BaseModel, ValidationError
from contextlib import asynccontextmanager
from redis.asyncio import Redis
from fastapi.responses import StreamingResponse
from core.service_mapping import config
from core.models import Article, Articles, ArticleEntity, ArticleTag
from core.adb import engine, get_session, create_db_and_tables
from sqlmodel import Session
from typing import AsyncGenerator
from sqlalchemy import insert, or_, func, delete
#import _and
from sqlalchemy import and_
from core.models import Article, Entity, ArticleEntity, EntityLocation, Tag, Location
import math
import uuid
import pandas as pd
from enum import Enum
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import joinedload
from fastapi.encoders import jsonable_encoder
import httpx

from fastapi import Query

from sqlalchemy.orm import selectinload

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Redis connection
redis_conn_flags = Redis(host='redis', port=config.REDIS_PORT, db=0)  # For flags


async def lifespan(app):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)

@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}, 200

@app.get("/flags")
async def produce_flags():
    await redis_conn_flags.delete("scrape_sources")
    flags = ["cnn", "bbc", "dw"]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

class SearchType(str, Enum):
    TEXT = "text"
    SEMANTIC = "semantic"

@app.get("/articles")
async def get_articles(
    url: Optional[str] = None,
    search_query: Optional[str] = None,
    search_type: SearchType = SearchType.TEXT,
    has_embeddings: Optional[bool] = Query(None, description="Filter articles with embeddings"),
    has_geocoding: Optional[bool] = Query(None, description="Filter articles with geocoding"),
    has_entities: Optional[bool] = Query(None, description="Filter articles with entities"),
    skip: int = 0, 
    limit: int = 10, 
    session: AsyncSession = Depends(get_session)
):
    logger.info(f"Received search_type: {search_type}, search_query: {search_query}")

    logger.info(f"Received search_type: {search_type}, search_query: {search_query}")

    async with session.begin():
        query = select(Article).options(
            selectinload(Article.entities).selectinload(Entity.locations),
            selectinload(Article.tags)
        )
        
        # Apply filters
        if url:
            query = query.where(Article.url == url)
        if has_geocoding:
            query = query.join(Article.entities).join(Entity.locations).distinct()
        if has_embeddings is not None:
            query = query.where(Article.embeddings.isnot(None) if has_embeddings else Article.embeddings.is_(None))
        if has_entities is not None:
            query = query.where(Article.entities.any() if has_entities else ~Article.entities.any())
        
        # Apply search based on search_type
        if search_query:
            if search_type == SearchType.TEXT:
                query = query.where(
                    or_(
                        Article.headline.ilike(f'%{search_query}%'), 
                        Article.paragraphs.ilike(f'%{search_query}%')
                    )
                )
            elif search_type == SearchType.SEMANTIC and has_embeddings != False:
                try:
                    # Get query embedding from NLP service
                    async with httpx.AsyncClient() as client:
                        response = await client.get(f"{config.service_urls['embedding_service']}/generate_query_embeddings", params={"query": search_query})
                        response.raise_for_status()
                        query_embeddings = response.json()["embeddings"]

                    embedding_array = query_embeddings
                    query = query.order_by(Article.embeddings.l2_distance(embedding_array))
                except httpx.HTTPError as e:
                    logger.error(f"Error calling NLP service: {e}")
                    raise HTTPException(status_code=500, detail="Failed to generate query embedding")
                except Exception as e:
                    logger.error(f"Unexpected error in semantic search: {e}")
                    raise HTTPException(status_code=500, detail="Unexpected error in semantic search")
        
        logger.info(f"Final query: {query}")
        
        # Execute the query
        try:
            result = await session.execute(query.offset(skip).limit(limit))
            articles = result.scalars().unique().all()
            logger.info(f"Number of articles retrieved: {len(articles)}")
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise HTTPException(status_code=500, detail="Error retrieving articles")
        
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
                ]
            }
            articles_data.append(article_dict)
        
        logger.info(f"Returning {len(articles_data)} articles")
        return articles_data
        
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
        await redis_conn.close()
        return {"message": "Raw articles processed successfully."}
    except Exception as e:
        logger.error(f"Error processing articles: {e}")
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await session.close()

@app.post("/store_articles_with_embeddings")
async def store_articles_with_embeddings(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=6)
        articles_with_embeddings = await redis_conn.lrange('articles_with_embeddings', 0, -1)
        await redis_conn.delete('articles_with_embeddings')

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
        await redis_conn.close()
        return {"message": "Articles with embeddings stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing articles with embeddings: {e}")
        raise HTTPException(status_code=400, detail=str(e))

from sqlalchemy import update, insert
from core.models import Article, Entity, ArticleEntity

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
        logger.info("Closing Redis connection")
        await redis_conn.close()
        logger.info("Articles with entities stored successfully")
        return {"message": "Articles with entities processed and stored successfully."}
    except Exception as e:
        logger.error(f"Error processing articles with entities: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/create_embedding_jobs")
async def create_embedding_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Trying to create embedding jobs.")
    try:
        async with session.begin():
            query = select(Article).where(Article.embeddings == None)
            result = await session.execute(query)
            articles_without_embeddings = result.scalars().all()
            logger.info(f"Found {len(articles_without_embeddings)} articles without embeddings.")

            articles_list = [
                json.dumps({
                    'url': article.url,
                    'headline': article.headline,
                    'paragraphs': article.paragraphs
                }) for article in articles_without_embeddings
            ]

        redis_conn_unprocessed_articles = await Redis(host='redis', port=config.REDIS_PORT, db=5)
        if articles_list:
            await redis_conn_unprocessed_articles.rpush('articles_without_embedding_queue', *articles_list)
            logger.info(f"Pushed {len(articles_list)} articles to Redis queue.")
        else:
            logger.info("No articles found that need embeddings.")

        await redis_conn_unprocessed_articles.close()
        return {"message": f"Embedding jobs created for {len(articles_list)} articles."}
    except Exception as e:
        logger.error(f"Failed to create embedding jobs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

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

@app.post("/create_entity_extraction_jobs")
async def create_entity_extraction_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create entity extraction jobs.")
    try:
        query = select(Article).where(Article.entities == None)
        result = await session.execute(query)
        articles_needing_entities = result.scalars().all()

        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=2)

        for article in articles_needing_entities:
            article_dict = {
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs
            }
            await redis_conn.lpush('articles_without_entities_queue', json.dumps(article_dict, ensure_ascii=False))

        await redis_conn.close()  # Close the Redis connection

        logger.info(f"Entity extraction jobs for {len(articles_needing_entities)} articles created.")
        return {"message": "Entity extraction jobs created successfully."}
    except Exception as e:
        logger.error(f"Error creating entity extraction jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create_geocoding_jobs")
async def create_geocoding_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create geocoding jobs.")
    try:
        async with session.begin():
            # Select articles with embeddings and entities
            query = select(Article).join(Article.entities).where(
                and_(
                    or_(
                        Entity.entity_type == 'GPE',
                        Entity.entity_type == 'LOC'
                    ),
                    ~Article.entities.any(Entity.locations.any())
                )
            ).distinct()
            result = await session.execute(query)
            articles = result.scalars().all()
            logger.info(f"Found {len(articles)} articles with embeddings and entities.")

            articles_list = []
            for article in articles:
                # Get GPE entities for this article
                gpe_entities = [entity for entity in article.entities if entity.entity_type == 'GPE' or 'LOC']
                
                if gpe_entities:
                    article_dict = {
                        'url': article.url,
                        'headline': article.headline,
                        'paragraphs': article.paragraphs,
                        'entities': [{'name': entity.name, 'entity_type': entity.entity_type} for entity in gpe_entities]
                    }
                    articles_list.append(json.dumps(article_dict, ensure_ascii=False))
                    logger.info(f"Article {article.url} has {len(gpe_entities)} GPE or LOC entities.")

        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=3)
        if articles_list:
            await redis_conn.rpush('articles_without_geocoding_queue', *articles_list)
            logger.info(f"Pushed {len(articles_list)} articles to Redis queue for geocoding.")
        else:
            logger.info("No articles found that need geocoding.")

        await redis_conn.close()
        return {"message": f"Geocoding jobs created for {len(articles_list)} articles."}
    except Exception as e:
        logger.error(f"Error creating geocoding jobs: {e}")
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
                                location = Location(name=location_data['name'], type="GPE", coordinates=location_data['coordinates'])
                                session.add(location)
                                await session.flush()  # Flush to get the location ID
                            
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

        await redis_conn.delete('articles_with_geocoding_queue')
        logger.info("Cleared Redis queue")
        await redis_conn.close()
        logger.info("Closed Redis connection")
        return {"message": "Geocoded articles stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing geocoded articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/create_semantic_machine_jobs")
async def create_semantic_machine_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create semantic machine jobs.")
    try:
        async with session.begin():
            # Select articles with no tags
            query = select(Article).where(Article.tags == None)
            result = await session.execute(query)
            articles = result.scalars().all()
            logger.info(f"Found {len(articles)} articles with no tags.")
            
            articles_list = [
                json.dumps({
                    'url': article.url,
                    'headline': article.headline,
                    'paragraphs': article.paragraphs
                    'source': article.source
                }) for article in articles
            ]
            
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=3)
        if articles_list:
            await redis_conn.rpush('articles_without_tags_queue', *articles_list)
            logger.info(f"Pushed {len(articles_list)} articles to Redis queue for semantic machine.")
        else:
            logger.info("No articles found that need semantic machine.")
        await redis_conn.close()
        return {"message": f"Semantic machine jobs created for {len(articles)} articles."}
    except Exception as e:
        logger.error(f"Error creating semantic machine jobs: {e}")
        raise HTTPException(status_code=400, detail=str(e))