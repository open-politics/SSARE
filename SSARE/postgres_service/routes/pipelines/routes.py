import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body, APIRouter
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
from core.utils import logger

## Setup 
# App API Router
router = APIRouter()
# Redis connection
redis_conn_flags = Redis(host='redis', port=config.REDIS_PORT, db=0)  # For flags


########################################################################################
## 1. SCRAPING PIPELINE

# Produce Flags for scraping
@router.get("/flags")
async def produce_flags():
    await redis_conn_flags.delete("scrape_sources")
    flags = ["cnn", "bbc", "dw", "pynews"]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@router.post("/store_raw_articles")
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

@router.post("/create_embedding_jobs")
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


@router.post("/store_articles_with_embeddings")
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

@router.post("/create_entity_extraction_jobs")
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


@router.post("/store_articles_with_entities")
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

@router.post("/create_geocoding_jobs")
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
    
@router.post("/store_articles_with_geocoding")
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

@router.post("/create_classification_jobs")
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

@router.post("/store_articles_with_classification")
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
