import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body, APIRouter
from sqlmodel import SQLModel, Field, create_engine, Session, select, update
from sqlmodel import Column, JSON
from contextlib import asynccontextmanager
from sqlalchemy import and_, delete, func, insert, or_, text, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from redis.asyncio import Redis
import uuid
import pandas as pd

from core.adb import engine, get_session, create_db_and_tables
from core.middleware import add_cors_middleware
from core.models import (
    Content, ContentClassification, ContentEntity, ContentTag, Entity,
    EntityLocation, Location, Tag, MediaDetails, VideoFrame, Image
)
from core.service_mapping import config
from core.utils import logger

## Setup
router = APIRouter()
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

@router.post("/store_raw_contents")
async def store_raw_contents(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=1, decode_responses=True)
        raw_contents = await redis_conn.lrange('raw_contents_queue', 0, -1)
        contents = [json.loads(content) for content in raw_contents]
        logger.info("Retrieved raw contents from Redis")

        async with session.begin():
            for content_data in contents:
                content_dict = {
                    k: str(v) if not pd.isna(v) else '' for k, v in content_data.items()
                }
                content = Content(**content_dict)
                existing_content = await session.execute(select(Content).where(Content.url == content.url))
                if existing_content.scalar_one_or_none() is not None:
                    logger.info(f"Updating existing content: {content.url}")
                    await session.execute(
                        update(Content).where(Content.url == content.url).values(**content.dict(exclude_unset=True))
                    )
                else:
                    logger.info(f"Adding new content: {content.url}")
                    session.add(content)
                await session.flush()

            await session.commit()

            await redis_conn.ltrim('raw_contents_queue', len(raw_contents), -1)
            await redis_conn.close()
            return {"message": "Raw contents processed successfully."}

    except Exception as e:
        logger.error(f"Error processing contents: {e}")
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await session.close()

########################################################################################
## 2. EMBEDDING PIPELINE

@router.post("/create_embedding_jobs")
async def create_embedding_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Creating embedding jobs.")
    try:
        async with session.begin():
            query = select(Content).where(Content.embeddings == None)
            result = await session.execute(query)
            contents_without_embeddings = result.scalars().all()
            logger.info(f"Found {len(contents_without_embeddings)} contents without embeddings.")

            redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=5)
            existing_urls = set(await redis_conn.lrange('contents_without_embedding_queue', 0, -1))
            existing_urls = {json.loads(url)['url'] for url in existing_urls}

            contents_list = []
            not_pushed_count = 0
            for content in contents_without_embeddings:
                if content.url not in existing_urls:
                    contents_list.append(json.dumps({
                        'url': content.url,
                        'title': content.title,
                        'text_content': content.text_content,
                        'content_type': content.content_type
                    }))
                else:
                    not_pushed_count += 1

            logger.info(f"{not_pushed_count} contents already in queue, not pushed again.")

        if contents_list:
            await redis_conn.rpush('contents_without_embedding_queue', *contents_list)
            logger.info(f"Pushed {len(contents_list)} contents to Redis queue.")
        else:
            logger.info("No new contents found that need embeddings.")

        await redis_conn.close()
        return {"message": f"Embedding jobs created for {len(contents_list)} contents."}

    except Exception as e:
        logger.error(f"Failed to create embedding jobs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/store_contents_with_embeddings")
async def store_contents_with_embeddings(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=6)
        contents_with_embeddings = await redis_conn.lrange('contents_with_embeddings', 0, -1)

        async with session.begin():
            for content_with_embeddings in contents_with_embeddings:
                try:
                    content_data = json.loads(content_with_embeddings)
                    logger.info(f"Storing content with embedding: {content_data['url']}")

                    existing_content = await session.execute(select(Content).where(Content.url == content_data['url']))
                    existing_content = existing_content.scalar_one_or_none()

                    if existing_content:
                        logger.info(f"Updating content with embedding: {content_data['url']}")
                        for key, value in content_data.items():
                            if key == 'embeddings':
                                setattr(existing_content, 'embeddings', value)
                            else:
                                setattr(existing_content, key, value)
                    else:
                        content = Content(**content_data)
                        session.add(content)

                except Exception as e:
                    logger.error(f"Error processing content: {e}")

            await session.commit()
            await redis_conn.ltrim('contents_with_embeddings', len(contents_with_embeddings), -1)
            await redis_conn.close()
            return {"message": "Contents with embeddings stored successfully in PostgreSQL."}

    except Exception as e:
        logger.error(f"Error storing contents with embeddings: {e}")
        raise HTTPException(status_code=400, detail=str(e))

########################################################################################
## 3. ENTITY PIPELINE

@router.post("/create_entity_extraction_jobs")
async def create_entity_extraction_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Creating entity extraction jobs.")
    try:
        async with session.begin():
            query = select(Content).where(Content.id.not_in(
                select(ContentEntity.content_id)
            ))
            result = await session.execute(query)
            contents = result.scalars().all()
            logger.info(f"Found {len(contents)} contents that need entity extraction.")

            redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=2)
            existing_urls = set(await redis_conn.lrange('contents_without_entities_queue', 0, -1))
            existing_urls = {json.loads(url)['url'] for url in existing_urls}

            contents_list = []
            not_pushed_count = 0
            for content in contents:
                if content.url not in existing_urls:
                    contents_list.append(json.dumps({
                        'url': content.url,
                        'title': content.title,
                        'text_content': content.text_content,
                        'content_type': content.content_type
                    }))
                else:
                    not_pushed_count += 1

            logger.info(f"{not_pushed_count} contents already in queue, not pushed again.")

        if contents_list:
            await redis_conn.rpush('contents_without_entities_queue', *contents_list)
            logger.info(f"Pushed {len(contents_list)} contents to Redis queue.")
        else:
            logger.info("No new contents found that need entity extraction.")

        await redis_conn.close()
        return {"message": f"Entity extraction jobs created for {len(contents_list)} contents."}

    except Exception as e:
        logger.error(f"Error creating entity extraction jobs: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/store_contents_with_entities")
async def store_contents_with_entities(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=2, decode_responses=True)
        contents = await redis_conn.lrange('contents_with_entities_queue', 0, -1)
        logger.info(f"Retrieved {len(contents)} contents from Redis queue")

        async with session.begin():
            for content_json in contents:
                try:
                    content_data = json.loads(content_json)
                    content = await session.execute(
                        select(Content).where(Content.url == content_data['url'])
                    )
                    content = content.scalar_one_or_none()

                    if content:
                        # Update content fields
                        for key, value in content_data.items():
                            if key not in ['entities', 'id']:
                                setattr(content, key, value)

                        # Handle entities
                        for entity_data in content_data.get('entities', []):
                            entity_stmt = select(Entity).where(
                                Entity.name == entity_data['text'],
                                Entity.entity_type == entity_data['tag']
                            )
                            result = await session.execute(entity_stmt)
                            entity = result.scalar_one_or_none()

                            if not entity:
                                entity = Entity(name=entity_data['text'], entity_type=entity_data['tag'])
                                session.add(entity)
                                await session.flush()

                            # Create ContentEntity link
                            content_entity = ContentEntity(content_id=content.id, entity_id=entity.id)
                            session.add(content_entity)
                    else:
                        logger.error(f"Content not found: {content_data['url']}")

                except Exception as e:
                    logger.error(f"Error processing content: {e}")

            await session.commit()
            await redis_conn.ltrim('contents_with_entities_queue', len(contents), -1)
            await redis_conn.close()
            return {"message": "Contents with entities processed and stored successfully."}

    except Exception as e:
        logger.error(f"Error storing contents with entities: {e}")
        raise HTTPException(status_code=400, detail=str(e))

########################################################################################
## 4. CLASSIFICATION PIPELINE

@router.post("/create_classification_jobs")
async def create_classification_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Creating classification jobs.")
    try:
        async with session.begin():
            query = select(Content).where(ContentClassification.content_id == None)
            result = await session.execute(query)
            contents = result.scalars().all()
            logger.info(f"Found {len(contents)} contents that need classification.")

            redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4)
            existing_urls = set(await redis_conn.lrange('contents_without_classification_queue', 0, -1))
            existing_urls = {json.loads(url)['url'] for url in existing_urls}

            contents_list = []
            not_pushed_count = 0
            for content in contents:
                if content.url not in existing_urls:
                    contents_list.append(json.dumps({
                        'url': content.url,
                        'title': content.title,
                        'text_content': content.text_content,
                        'content_type': content.content_type
                    }))
                else:
                    not_pushed_count += 1

            logger.info(f"{not_pushed_count} contents already in queue, not pushed again.")

        if contents_list:
            await redis_conn.rpush('contents_without_classification_queue', *contents_list)
            logger.info(f"Pushed {len(contents_list)} contents to Redis queue.")
        else:
            logger.info("No new contents found that need classification.")

        await redis_conn.close()
        return {"message": f"Classification jobs created for {len(contents_list)} contents."}

    except Exception as e:
        logger.error(f"Error creating classification jobs: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/store_contents_with_classification")
async def store_contents_with_classification(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4, decode_responses=True)
        classified_contents = await redis_conn.lrange('contents_with_classification_queue', 0, -1)
        logger.info(f"Retrieved {len(classified_contents)} classified contents from Redis queue")

        async with session.begin():
            for content_json in classified_contents:
                try:
                    content_data = json.loads(content_json)
                    content = await session.execute(
                        select(Content).options(selectinload(Content.classification)).where(Content.url == content_data['url'])
                    )
                    content = content.scalar_one_or_none()

                    if content:
                        classification_data = content_data['classification']
                        if content.classification:
                            # Update existing classification
                            for key, value in classification_data.items():
                                setattr(content.classification, key, value)
                        else:
                            # Create new classification
                            content.classification = ContentClassification(**classification_data)

                        session.add(content)
                        logger.info(f"Updated content and classification: {content_data['url']}")
                    else:
                        logger.warning(f"Content not found in database: {content_data['url']}")

                except Exception as e:
                    logger.error(f"Error processing content: {e}")

            await session.commit()
            await redis_conn.ltrim('contents_with_classification_queue', len(classified_contents), -1)
            await redis_conn.close()
            return {"message": "Classified contents stored successfully in PostgreSQL."}

    except Exception as e:
        logger.error(f"Error storing classified contents: {e}")
        raise HTTPException(status_code=400, detail=str(e))
