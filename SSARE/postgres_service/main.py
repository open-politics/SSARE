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
from core.models import Article, Articles
from core.adb import engine, get_session, create_db_and_tables
from sqlmodel import Session
from typing import AsyncGenerator
from sqlalchemy import insert, or_, func, delete
from core.models import Article, Entity, ArticleEntity, EntityLocation, Tag, Location
import math
import uuid
import pandas as pd
from sqlalchemy.orm import joinedload

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

from sqlalchemy.orm import joinedload
from fastapi.encoders import jsonable_encoder

from fastapi import Query

from sqlalchemy.orm import selectinload

@app.get("/articles")
async def get_articles(
    url: Optional[str] = None,
    search_text: Optional[str] = None,
    has_embedding: Optional[bool] = Query(None, description="Filter articles with embeddings"),
    has_geocoding: Optional[bool] = Query(None, description="Filter articles with geocoding"),
    has_entities: Optional[bool] = Query(None, description="Filter articles with entities"),
    skip: int = 0, 
    limit: int = 10, 
    session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        query = select(Article).options(
            selectinload(Article.entities).selectinload(Entity.locations),
            selectinload(Article.tags)
        )
        
        logger.info(f"Initial query: {query}")
        
        # Add filters
        if url:
            query = query.where(Article.url == url)

        if has_geocoding:
            query = query.join(Article.entities).join(Entity.locations).distinct()
        if search_text:
            query = query.where(
                or_(
                    Article.headline.ilike(f'%{search_text}%'), 
                    Article.paragraphs.ilike(f'%{search_text}%')
                )
            )
        
        logger.info(f"Query after filters: {query}")
        
        # Execute the query
        result = await session.execute(query)
        articles = result.unique().scalars().all()
        
        articles_data = []
        for article in articles:
            article_dict = {
                "id": str(article.id),
                "url": article.url,
                "headline": article.headline,
                "source": article.source,
                "insertion_date": article.insertion_date,
                "paragraphs": article.paragraphs,
                "embedding": article.embedding[:5].tolist() if article.embedding is not None else None,
                "entities": [
                    {
                        "id": str(e.id),
                        "name": e.name,
                        "entity_type": e.entity_type,
                        "locations": [
                            {
                                "name": loc.name,
                                "type": loc.type,
                                "coordinates": loc.coordinates
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
async def store_processed_articles(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=6)
        articles_with_embeddings = await redis_conn.lrange('articles_with_embeddings', 0, -1)
        await redis_conn.delete('articles_with_embeddings')

        async with session.begin():
            for article_with_embedding in articles_with_embeddings:
                try:
                    article_data = json.loads(article_with_embedding)
                    logger.info(f"Storing article with embeddings: {article_data['url']}")

                    existing_article = await session.execute(select(Article).where(Article.url == article_data['url']))
                    existing_article = existing_article.scalar_one_or_none()

                    if existing_article:
                        logger.info(f"Updating article with embeddings: {article_data['url']}")
                        for key, value in article_data.items():
                            if key == 'embeddings':
                                setattr(existing_article, 'embeddings', value)
                                setattr(existing_article, 'embeddings_created', 1)
                                setattr(existing_article, 'pgvectors_available', 1)
                            else:
                                setattr(existing_article, key, value)
                    else:
                        article_data['embeddings_created'] = 1 if 'embeddings' in article_data else 0
                        article_data['pgvectors_available'] = 1 if 'embeddings' in article_data else 0
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

@app.post("/update_pgvector_flags")
async def update_pgvector_flags(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article).where(Article.embeddings_created == 1, Article.pgvectors_available == 0)
            result = await session.execute(query)
            articles_to_update = result.scalars().all()
            
            if not articles_to_update:
                logger.info("No articles found that need pgvector flags updated.")
                return {"message": "No articles to update."}
            
            urls_to_update = [article.url for article in articles_to_update]
            
            update_query = update(Article).where(Article.url.in_(urls_to_update)).values(pgvectors_available=1)
            update_result = await session.execute(update_query)
            
            await session.commit()
            
            logger.info(f"Updated pgvector flags for {update_result.rowcount} articles.")
            return {"message": f"pgvector flags updated for {update_result.rowcount} articles."}
    except Exception as e:
        logger.error(f"Error updating pgvector flags: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create_embedding_jobs")
async def create_embedding_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Trying to create embedding jobs.")
    try:
        async with session.begin():
            query = select(Article).where(Article.embedding.is_(None))
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
        query = select(Article).where(Article.embedding.isnot(None))
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
            query = select(Article).options(selectinload(Article.entities)).where(Article.entities.any())
            result = await session.execute(query)
            articles = result.scalars().all()
            logger.info(f"Found {len(articles)} articles with embeddings and entities.")

            articles_list = []
            for article in articles:
                # Get GPE entities for this article
                gpe_entities = [entity for entity in article.entities if entity.entity_type == 'GPE']
                
                if gpe_entities:
                    article_dict = {
                        'url': article.url,
                        'headline': article.headline,
                        'paragraphs': article.paragraphs,
                        'entities': [{'name': entity.name, 'entity_type': entity.entity_type} for entity in gpe_entities]
                    }
                    articles_list.append(json.dumps(article_dict, ensure_ascii=False))
                    logger.info(f"Article {article.url} has {len(gpe_entities)} GPE entities.")

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
    
@app.post("/store_geocoded_articles")
async def store_geocoded_articles(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4)
        geocoded_articles = await redis_conn.lrange('articles_with_geocoding_queue', 0, -1)
        await redis_conn.delete('articles_with_geocoding_queue')

        async with session.begin():
            for geocoded_article in geocoded_articles:
                try:
                    geocoded_data = json.loads(geocoded_article)
                    logger.info(f"Storing geocoded data for article: {geocoded_data['url']}")

                    article = await session.execute(select(Article).where(Article.url == geocoded_data['url']))
                    article = article.scalar_one_or_none()

                    if article:
                        for location_data in geocoded_data['geocoded_locations']:
                            entity = await session.execute(select(Entity).where(Entity.name == location_data['name'], Entity.entity_type == "GPE"))
                            entity = entity.scalar_one_or_none()
                            
                            if not entity:
                                entity = Entity(name=location_data['name'], entity_type="GPE")
                                session.add(entity)
                            
                            location = await session.execute(select(Location).where(Location.name == location_data['name']))
                            location = location.scalar_one_or_none()
                            
                            if not location:
                                location = Location(name=location_data['name'], type="GPE", coordinates=location_data['coordinates'])
                                session.add(location)
                            
                            if entity not in article.entities:
                                article.entities.append(entity)
                            if location not in entity.locations:
                                entity.locations.append(location)
                        
                        article.geocoding_created = 1
                        session.add(article)
                    else:
                        logger.error(f"Article not found: {geocoded_data['url']}")

                except Exception as e:
                    logger.error(f"Error processing geocoded article {geocoded_data['url']}: {str(e)}")

        await session.commit()
        await redis_conn.close()
        return {"message": "Geocoded articles stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing geocoded articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))