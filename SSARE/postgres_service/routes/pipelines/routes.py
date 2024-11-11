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
from uuid import UUID
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
from core.models import Content, ContentEntity, Entity, Location, Tag, ContentEvaluation, EntityLocation, ContentTag, ContentChunk
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

@router.post("/store_raw_contents")
async def store_raw_contents(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=1, decode_responses=True)
        raw_contents = await redis_conn.lrange('raw_contents_queue', 0, -1)
        contents = [json.loads(content) for content in raw_contents]
        contents = [Content(**content) for content in contents]
        logger.info("Retrieved raw contents from Redis")
        logger.info(f"First 1 content: {[{k: v for k, v in content.dict().items() if k in ['url', 'title']} for content in contents[:1]]}")

        async with session.begin():
            for content in contents:
                try:
                    # Check if content already exists
                    existing_content = await session.execute(select(Content).where(Content.url == content.url))
                    if existing_content.scalar_one_or_none() is not None:
                        logger.info(f"Updating existing content: {content.url}")
                        await session.execute(update(Content).where(Content.url == content.url).values(**content.dict(exclude_unset=True)))
                    else:
                        logger.info(f"Adding new content: {content.url}")
                        session.add(content)
                    await session.flush()
                except Exception as e:
                    logger.error(f"Error processing content {content.url}: {str(e)}")
                   

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
    logger.info("Trying to create embedding jobs.")
    try:
        async with session.begin():
            # Modified query to select contents that have neither embeddings nor chunks
            query = select(Content).where(
                and_(
                    Content.embeddings == None,
                    ~Content.chunks.any()  # to check if there are no chunks at all
                )
            )
            result = await session.execute(query)
            contents_without_embeddings = result.scalars().all()
            logger.info(f"Found {len(contents_without_embeddings)} contents without embeddings.")

            redis_conn_unprocessed_contents = await Redis(host='redis', port=config.REDIS_PORT, db=5)

            # Get existing contents in the queue
            existing_urls = set(await redis_conn_unprocessed_contents.lrange('contents_without_embedding_queue', 0, -1))
            existing_urls = {json.loads(url)['url'] for url in existing_urls}

            contents_list = []
            not_pushed_count = 0
            for content in contents_without_embeddings:
                if content.url not in existing_urls:
                    contents_list.append(json.dumps({
                        'url': content.url,
                        'title': content.title,
                        'text_content': content.text_content
                    }))
                else:
                    not_pushed_count += 1

            logger.info(f"{not_pushed_count} contents already in queue, not pushed again.")

        if contents_list:
            await redis_conn_unprocessed_contents.rpush('contents_without_embedding_queue', *contents_list)
            logger.info(f"Pushed {len(contents_list)} contents to Redis queue.")
        else:
            logger.info("No new contents found that need embeddings.")

        await redis_conn_unprocessed_contents.close()
        return {"message": f"Embedding jobs created for {len(contents_list)} contents."}
    except Exception as e:
        logger.error(f"Failed to create embedding jobs: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/store_contents_with_embeddings")
async def store_contents_with_embeddings(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=6, decode_responses=True)
        contents_with_embeddings = await redis_conn.lrange('contents_with_embeddings', 0, -1)

        async with session.begin():
            for index, content_json in enumerate(contents_with_embeddings, 1):
                try:
                    content_data = json.loads(content_json)
                    logger.info(f"Processing content {index}/{len(contents_with_embeddings)}: {content_data.get('url')}")

                    # Find the content by URL and eagerly load the chunks
                    result = await session.execute(
                        select(Content).options(selectinload(Content.chunks)).where(Content.url == content_data['url'])
                    )
                    content = result.scalar_one_or_none()

                    if content:
                        # Handle chunks
                        for chunk_data in content_data.get('chunks', []):
                            chunk_data['content_id'] = content.id  # Associate with the content
                            chunk_number = chunk_data['chunk_number']
                            # Check if chunk exists
                            existing_chunk = await session.execute(
                                select(ContentChunk).where(
                                    ContentChunk.content_id == content.id,
                                    ContentChunk.chunk_number == chunk_number
                                )
                            )
                            existing_chunk = existing_chunk.scalar_one_or_none()
                            if existing_chunk:
                                for key, value in chunk_data.items():
                                    setattr(existing_chunk, key, value)
                                logger.info(f"Updated existing chunk number {chunk_number} for content {content.url}")
                            else:
                                chunk = ContentChunk(**chunk_data)
                                session.add(chunk)
                                logger.info(f"Added new chunk number {chunk_number} for content {content.url}")

                except ValidationError as e:
                    logger.error(f"Validation error for content: {e}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error: {e}")
                except Exception as e:
                    logger.error(f"Error processing content: {e}", exc_info=True)

        await session.commit()
        logger.info("Stored contents with embeddings in PostgreSQL")

        # Clear the processed contents from Redis
        await redis_conn.ltrim('contents_with_embeddings', len(contents_with_embeddings), -1)
        await redis_conn.close()
    except Exception as e:
        logger.error(f"Error storing contents with embeddings: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await session.close()

########################################################################################
## 3. ENTITY PIPELINE

@router.post("/create_entity_extraction_jobs")
async def create_entity_extraction_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create entity extraction jobs.")
    try:
        query = select(Content).where(Content.entities == None)
        result = await session.execute(query)
        _contents = result.scalars().all()

        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=2)

        # Get existing contents in the queue
        existing_urls = set(await redis_conn.lrange('contents_without_entities_queue', 0, -1))
        existing_urls = {json.loads(url)['url'] for url in existing_urls}   
        
        contents_list = []
        not_pushed_count = 0
        for content in _contents:
            if content.url not in existing_urls:
                contents_list.append(json.dumps({
                    'url': content.url,
                    'title': content.title,
                    'text_content': content.text_content
                }))
            else:
                not_pushed_count += 1

        logger.info(f"{not_pushed_count} contents already in queue, not pushed again.")

        if contents_list:
            await redis_conn.rpush('contents_without_entities_queue', *contents_list)
            logger.info(f"Pushed {len(contents_list)} contents to Redis queue.")
        else:
            logger.info("No new contents found that need entities.")

        await redis_conn.close()  # Close the Redis connection

        logger.info(f"Entity extraction jobs for {len(_contents)} contents created.")
        return {"message": "Entity extraction jobs created successfully."}
    except Exception as e:
        logger.error(f"Error creating entity extraction jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/store_contents_with_entities")
async def store_contents_with_entities(session: AsyncSession = Depends(get_session)):
    try:
        logger.info("Starting store_contents_with_entities function")
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=2, decode_responses=True)
        logger.info(f"Connected to Redis on port {config.REDIS_PORT}, db 2")
        contents = await redis_conn.lrange('contents_with_entities_queue', 0, -1)
        logger.info(f"Retrieved {len(contents)} contents from Redis queue")
        
        async with session.begin():
            logger.info("Starting database session")
            for index, content_json in enumerate(contents, 1):
                try:
                    content_data = json.loads(content_json)
                    logger.info(f"Processing content {index}/{len(contents)}: {content_data['url']}")
                    
                    # Update content fields excluding entities and id
                    content_update = {k: v for k, v in content_data.items() if k not in ['entities', 'id']}
                    stmt = update(Content).where(Content.url == content_data['url']).values(**content_update)
                    await session.execute(stmt)
                    
                    # Handle entities separately
                    if 'entities' in content_data:
                        # Get the content id
                        result = await session.execute(select(Content.id).where(Content.url == content_data['url']))
                        content_id = result.scalar_one()
                        
                        # Delete existing ContentEntity entries for this content
                        await session.execute(delete(ContentEntity).where(ContentEntity.content_id == content_id))
                        
                        for entity_data in content_data['entities']:
                            # Create or get entity
                            entity_stmt = select(Entity).where(Entity.name == entity_data['text'], Entity.entity_type == entity_data['tag'])
                            result = await session.execute(entity_stmt)
                            entity = result.scalar_one_or_none()
                            
                            if not entity:
                                entity = Entity(name=entity_data['text'], entity_type=entity_data['tag'])
                                session.add(entity)
                                await session.flush()  # This will populate the id of the new entity
                            
                            # Create or update ContentEntity link
                            content_entity_stmt = select(ContentEntity).where(
                                ContentEntity.content_id == content_id,
                                ContentEntity.entity_id == entity.id
                            )
                            result = await session.execute(content_entity_stmt)
                            existing_content_entity = result.scalar_one_or_none()

                            if existing_content_entity:
                                existing_content_entity.frequency += 1
                            else:
                                content_entity = ContentEntity(content_id=content_id, entity_id=entity.id)
                                session.add(content_entity)
                    
                except ValidationError as e:
                    logger.error(f"Validation error for content {content_data['url']}: {e}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error for content: {e}")

        logger.info("Changes committed to database")
        await redis_conn.ltrim('contents_with_entities_queue', len(contents), -1)
        logger.info("Redis queue trimmed")
        logger.info("Closing Redis connection")
        await redis_conn.close()
        logger.info("Contents with entities stored successfully")
        return {"message": "Contents with entities processed and stored successfully."}
    except Exception as e:
        logger.error(f"Error processing contents with entities: {e}")
        raise HTTPException(status_code=400, detail=str(e))

########################################################################################
## 4. GEOCODING PIPELINE

@router.post("/create_geocoding_jobs")
async def create_geocoding_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create geocoding jobs.")
    try:
        async with session.begin():
            # Select contents with entities that are locations and do not have geocoding
            query = select(Content).options(
                selectinload(Content.entities).selectinload(Entity.locations)
            ).where(
                Content.entities.any(
                    and_(
                        or_(
                            Entity.entity_type == 'GPE',
                            Entity.entity_type == 'LOC'
                        ),
                        ~Entity.locations.any()  # Check if the entity has no locations
                    )
                )
            )
            
            
            result = await session.execute(query)
            contents = result.scalars().all()
            logger.info(f"Found {len(contents)} contents with entities that need geocoding.")

            redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=3)

            # Get existing contents in the queue
            existing_urls = set(await redis_conn.lrange('contents_without_geocoding_queue', 0, -1))
            existing_urls = {json.loads(url)['url'] for url in existing_urls}

            contents_list = []
            not_pushed_count = 0
            for content in contents:
                if content.url not in existing_urls:
                    location_entities = [entity for entity in content.entities if entity.entity_type in ('GPE', 'LOC') and not entity.locations]
                    
                    if location_entities:
                        content_dict = {
                            'url': content.url,
                            'title': content.title,
                            'text_content': content.text_content,
                            'entities': [{'text': entity.name, 'tag': entity.entity_type} for entity in location_entities]
                        }
                        contents_list.append(json.dumps(content_dict, ensure_ascii=False))
                        logger.info(f"Content {content.url} has {len(location_entities)} location entities that need geocoding.")
                else:
                    not_pushed_count += 1

            if contents_list:
                await redis_conn.rpush('contents_without_geocoding_queue', *contents_list)
                logger.info(f"Pushed {len(contents_list)} new contents to Redis queue for geocoding.")
            else:
                logger.info("No new contents found that need geocoding.")
            
            logger.info(f"{not_pushed_count} contents were not pushed to the queue as they were already present.")

            await redis_conn.close()
            return {"message": f"Geocoding jobs created for {len(contents_list)} new contents. {not_pushed_count} contents were already in the queue."}
    except Exception as e:
        logger.error(f"Error creating geocoding jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    
@router.post("/store_contents_with_geocoding")
async def store_contents_with_geocoding(session: AsyncSession = Depends(get_session)):
    try:
        logger.info("Starting store_contents_with_geocoding function")
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4, decode_responses=True)
        logger.info(f"Connected to Redis on port {config.REDIS_PORT}, db 4")
        geocoded_contents = await redis_conn.lrange('contents_with_geocoding_queue', 0, -1)
        logger.info(f"Retrieved {len(geocoded_contents)} geocoded contents from Redis queue")
        
        for index, geocoded_content in enumerate(geocoded_contents, 1):
            try:
                geocoded_data = json.loads(geocoded_content)
                logger.info(f"Processing geocoded content {index}/{len(geocoded_contents)}: {geocoded_data['url']}")
                
                async with session.begin():
                    content = await session.execute(
                        select(Content).where(Content.url == geocoded_data['url'])
                    )
                    content = content.scalar_one_or_none()

                    if content:
                        for location_data in geocoded_data['geocoded_locations']:
                            entity = await session.execute(
                                select(Entity).where(Entity.name == location_data['name'], Entity.entity_type == "location")
                            )
                            entity = entity.scalar_one_or_none()
                            
                            if not entity:
                                entity = Entity(name=location_data['name'], entity_type="location")
                                session.add(entity)
                                await session.flush()  # Flush to get the entity ID
                            
                            location = await session.execute(
                                select(Location).where(Location.name == location_data['name'])
                            )
                            location = location.scalar_one_or_none()
                            
                            if not location:
                                location = Location(
                                    name=location_data['name'],
                                    location_type=location_data.get('location_type', 'location'),  # Ensure a default value
                                    coordinates=location_data['coordinates']['coordinates'],
                                    weight=location_data['weight']
                                )
                                session.add(location)
                                await session.flush()  # Flush to get the location ID
                            else:
                                # Update the weight if the new weight is higher
                                location.weight = max(location.weight, location_data['weight'])
                            
                            # Check if ContentEntity already exists
                            existing_content_entity = await session.execute(
                                select(ContentEntity).where(
                                    ContentEntity.content_id == content.id,
                                    ContentEntity.entity_id == entity.id
                                )
                            )
                            existing_content_entity = existing_content_entity.scalar_one_or_none()

                            if existing_content_entity:
                                # Update frequency if it already exists
                                await session.execute(
                                    update(ContentEntity).
                                    where(ContentEntity.content_id == content.id, ContentEntity.entity_id == entity.id).
                                    values(frequency=ContentEntity.frequency + 1)
                                )
                            else:
                                # Create new ContentEntity if it doesn't exist
                                content_entity = ContentEntity(content_id=content.id, entity_id=entity.id)
                                session.add(content_entity)

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
                        
                        # Check if ContentTag already exists
                        existing_content_tag = await session.execute(
                            select(ContentTag).where(
                                ContentTag.content_id == content.id,
                                ContentTag.tag_id == tag.id
                            )
                        )
                        existing_content_tag = existing_content_tag.scalar_one_or_none()

                        if not existing_content_tag:
                            content_tag = ContentTag(content_id=content.id, tag_id=tag.id)
                            session.add(content_tag)
                    else:
                        logger.error(f"Content not found: {geocoded_data['url']}")
                
            except Exception as e:
                logger.error(f"Error processing geocoded content {geocoded_data['url']}: {str(e)}")
                # Continue processing other contents

        await redis_conn.ltrim('contents_with_geocoding_queue', len(geocoded_contents), -1)
        logger.info("Cleared Redis queue")
        await redis_conn.close()
        logger.info("Closed Redis connection")
        return {"message": "Geocoded contents stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing geocoded contents: {e}")
        raise HTTPException(status_code=400, detail=str(e))

########################################################################################
## 5. LLM CLASSIFICATION PIPELINE

@router.post("/create_classification_jobs")
async def create_classification_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create classification jobs.")
    try:
        async with session.begin():
            # Select contents with no tags
            query = select(Content).where(Content.evaluation == None)
            result = await session.execute(query)
            _contents = result.scalars().all()
            logger.info(f"Found {len(_contents)} contents with no classification.")

            redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4)
            existing_urls = set(await redis_conn.lrange('contents_without_classification_queue', 0, -1))
            existing_urls = {json.loads(url)['url'] for url in existing_urls}

            contents_list = []
            not_pushed_count = 0
            for content in _contents:
                if content.url not in existing_urls:
                    contents_list.append(json.dumps({
                        'url': content.url,
                        'title': content.title,
                        'text_content': content.text_content,
                        'source': content.source
                    }))
                else:
                    not_pushed_count += 1
            
        if contents_list:
            await redis_conn.rpush('contents_without_classification_queue', *contents_list)
            logger.info(f"Pushed {len(contents_list)} contents to Redis queue for classification.")
        else:
            logger.info("No contents found that need classification.")
        await redis_conn.close()
        return {"message": f"Classification jobs created for {len(_contents)} contents."}
    except Exception as e:
        logger.error(f"Error creating classification jobs: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/store_contents_with_classification")
async def store_contents_with_classification(session: AsyncSession = Depends(get_session)):
    try:
        logger.info("Starting store_contents_with_classification function")
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=4, decode_responses=True)
        classified_contents = await redis_conn.lrange('contents_with_classification_queue', 0, -1)
        logger.info(f"Retrieved {len(classified_contents)} classified contents from Redis queue")
        
        for index, classified_content in enumerate(classified_contents, 1):
            try:
                content_data = json.loads(classified_content)
                logger.info(f"Processing content {index}/{len(classified_contents)}: {content_data['url']}")
                logger.debug(f"Content evaluation data: {content_data.get('evaluations', {})}")
                
                # Find the content by URL
                stmt = select(Content).where(Content.url == content_data['url'])
                result = await session.execute(stmt)
                content = result.scalar_one_or_none()

                if content:
                    evaluation_data = content_data.get('evaluations', {})
                    evaluation_data = {
                        'content_id': content.id,
                        'rhetoric': evaluation_data.get('rhetoric', 'neutral'), 
                        'sociocultural_interest': evaluation_data.get('sociocultural_interest', 0),
                        'global_political_impact': evaluation_data.get('global_political_impact', 0),
                        'regional_political_impact': evaluation_data.get('regional_political_impact', 0),
                        'global_economic_impact': evaluation_data.get('global_economic_impact', 0),
                        'regional_economic_impact': evaluation_data.get('regional_economic_impact', 0),
                        'event_type': evaluation_data.get('event_type', 'other'),
                        'event_subtype': evaluation_data.get('event_subtype', 'other'),
                        'keywords': evaluation_data.get('keywords', []),
                        'categories': evaluation_data.get('categories', [])
                    }
                    
                    # Check if evaluation exists
                    stmt = select(ContentEvaluation).where(ContentEvaluation.content_id == content.id)
                    result = await session.execute(stmt)
                    existing_eval = result.scalar_one_or_none()
                    
                    if existing_eval:
                        # Update existing evaluation
                        stmt = (
                            update(ContentEvaluation)
                            .where(ContentEvaluation.content_id == content.id)
                            .values(**evaluation_data)
                        )
                        await session.execute(stmt)
                    else:
                        # Create new evaluation
                        evaluation = ContentEvaluation(**evaluation_data)
                        session.add(evaluation)
                    
                    await session.flush()
                    logger.info(f"Updated content and evaluation: {content_data['url']}")
                else:
                    logger.warning(f"Content not found in database: {content_data['url']}")

            except Exception as e:
                logger.error(f"Error processing content {content_data.get('url', 'unknown')}: {str(e)}")
                continue

        await session.commit()
        logger.info("Changes committed to database")
        
        # Clear processed contents from Redis
        await redis_conn.ltrim('contents_with_classification_queue', len(classified_contents), -1)
        logger.info("Redis queue trimmed")
        await redis_conn.close()
        
        return {"message": "Classified contents stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing classified contents: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))












