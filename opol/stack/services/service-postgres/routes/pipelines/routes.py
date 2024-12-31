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
from sqlalchemy.dialects.postgresql import insert

from core.adb import engine, get_session, create_db_and_tables
from core.middleware import add_cors_middleware
from core.models import Content, ContentEntity, Entity, Location, Tag, ContentEvaluation, EntityLocation, ContentTag, ContentChunk, MediaDetails, Image, TopContentEntity, TopContentLocation
from core.service_mapping import config
from core.utils import logger
from core.service_mapping import get_redis_url

## Setup 
# App API Router
router = APIRouter()
# Redis connection
redis_conn_flags = Redis.from_url(get_redis_url(), db=0)  # For flags


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
        redis_conn = await Redis.from_url(get_redis_url(), db=1, decode_responses=True)
        raw_contents = await redis_conn.lrange('raw_contents_queue', 0, -1)
        contents = [json.loads(content) for content in raw_contents]
        
        async with session.begin():
            for content_data in contents:
                # Check if the URL already exists
                existing_content = await session.execute(
                    select(Content).where(Content.url == content_data['url'])
                )
                if existing_content.scalar_one_or_none():
                    logger.info(f"Content with URL {content_data['url']} already exists. Skipping insertion.")
                    continue

                content = Content(**content_data)
                media_details = content_data.get('media_details')
                if media_details:
                    media_details_obj = MediaDetails(
                        top_image=media_details.get('top_image'),
                        images=[Image(image_url=img) for img in media_details.get('images', [])]
                    )
                    content.media_details = media_details_obj
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
    logger.info("Trying to create embedding jobs.")
    try:
        async with session.begin():
            # Modified query to select contents that have no chunks with embeddings
            query = select(Content).where(Content.embeddings == None)
            result = await session.execute(query)
            contents_without_embeddings = result.scalars().all()
            logger.info(f"Found {len(contents_without_embeddings)} contents without chunk embeddings.")

            redis_conn_unprocessed_contents = await Redis.from_url(get_redis_url(), db=5)

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
        redis_conn = await Redis.from_url(get_redis_url(), db=6, decode_responses=True)
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
                        # Update the overall content embeddings
                        content.embeddings = content_data.get('embeddings')

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

        redis_conn = await Redis.from_url(get_redis_url(), db=2)

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
        redis_conn = await Redis.from_url(get_redis_url(), db=2, decode_responses=True)
        logger.info(f"Connected to Redis on port {config.REDIS_PORT}, db 2")
        contents = await redis_conn.lrange('contents_with_entities_queue', 0, -1)
        logger.info(f"Retrieved {len(contents)} contents from Redis queue")
        
        async with session.begin():
            for index, content_json in enumerate(contents, 1):
                try:
                    content_data = json.loads(content_json)
                    logger.info(f"Processing content {index}/{len(contents)}: {content_data['url']}")

                    # Find the content by URL and eagerly load the chunks
                    result = await session.execute(
                        select(Content).options(selectinload(Content.chunks)).where(Content.url == content_data['url'])
                    )
                    content = result.scalar_one_or_none()

                    if content:
                        # Update the overall content embeddings
                        content.embeddings = content_data.get('embeddings')

                        # Handle entities
                        if 'entities' in content_data:
                            # Get the content id
                            content_id = content.id
                            
                            for entity_data in content_data['entities']:
                                # Get or create Entity
                                entity_stmt = select(Entity).where(
                                    Entity.name == entity_data['text'],
                                )
                                result = await session.execute(entity_stmt)
                                entity = result.scalar_one_or_none()

                                if not entity:
                                    entity = Entity(name=entity_data['text'], entity_type=entity_data['tag'])
                                    session.add(entity)
                                    await session.flush()  # Populate `entity.id`
                            

                                # Upsert ContentEntity
                                upsert_stmt = insert(ContentEntity).values(
                                    content_id=content_id,
                                    entity_id=entity.id,
                                    frequency=1
                                ).on_conflict_do_update(
                                    index_elements=['content_id', 'entity_id'],
                                    set_={'frequency': ContentEntity.frequency + 1}
                                )
                                await session.execute(upsert_stmt)

                        # Handle top entities
                        if 'top_entities' in content_data:
                            top_entities = content_data['top_entities']
                            for entity_name in top_entities:
                                entity_stmt = select(Entity).where(Entity.name == entity_name)
                                result = await session.execute(entity_stmt)
                                entity = result.scalar_one_or_none()
                                
                                if not entity:
                                    entity = Entity(name=entity_name, entity_type="unknown")
                                    session.add(entity)
                                    await session.flush()
                                
                                # Check if the top content entity already exists
                                existing_top_content_entity = await session.execute(
                                    select(TopContentEntity).where(
                                        TopContentEntity.content_id == content.id,
                                        TopContentEntity.entity_id == entity.id
                                    )
                                )
                                if existing_top_content_entity.scalar_one_or_none():
                                    logger.info(f"TopContentEntity for content {content.url} and entity {entity.name} already exists. Skipping insertion.")
                                    continue

                                # Insert new top content entity
                                content_entity = TopContentEntity(content_id=content.id, entity_id=entity.id)
                                session.add(content_entity)

                        # Handle top locations
                        if 'top_locations' in content_data:
                            top_locations = content_data['top_locations']
                            for location_name in top_locations:
                                location_stmt = select(Location).where(Location.name == location_name)
                                result = await session.execute(location_stmt)
                                location = result.scalar_one_or_none()
                                
                                if not location:
                                    location = Location(name=location_name, location_type="unknown")
                                    session.add(location)
                                    await session.flush()
                                
                                # Check if the top content location already exists
                                existing_top_content_location = await session.execute(
                                    select(TopContentLocation).where(
                                        TopContentLocation.content_id == content.id,
                                        TopContentLocation.location_id == location.id
                                    )
                                )
                                if existing_top_content_location.scalar_one_or_none():
                                    logger.info(f"TopContentLocation for content {content.url} and location {location.name} already exists. Skipping insertion.")
                                    continue

                                # Insert new top content location
                                content_location = TopContentLocation(content_id=content.id, location_id=location.id)
                                session.add(content_location)
                    
                    else:
                        logger.error(f"Content not found: {content_data['url']}")

                except ValidationError as e:
                    logger.error(f"Validation error for content {content_data['url']}: {e}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error for content: {e}")
                except Exception as e:
                    logger.error(f"Error processing content {content_data.get('url', 'unknown')}: {str(e)}", exc_info=True)

        await session.commit()
        logger.info("Stored contents with entities in PostgreSQL")

        # Clear the processed contents from Redis
        await redis_conn.ltrim('contents_with_entities_queue', len(contents), -1)
        logger.info("Redis queue trimmed")
        await redis_conn.close()
        logger.info("Contents with entities stored successfully")
        return {"message": "Contents with entities processed and stored successfully."}
    except Exception as e:
        logger.error(f"Error storing contents with entities: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await session.close()

########################################################################################
## 4. GEOCODING PIPELINE

@router.post("/create_geocoding_jobs")
async def create_geocoding_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create geocoding jobs.")
    try:
        async with session.begin():
            # Select locations that lack geocoding
            query = select(Location).where(Location.coordinates == None)
            result = await session.execute(query)
            locations = result.scalars().all()
            logger.info(f"Found {len(locations)} locations needing geocoding.")

            redis_conn = await Redis.from_url(get_redis_url(), db=3)

            # Get existing locations in the queue
            existing_locations = set(await redis_conn.lrange('locations_without_geocoding_queue', 0, -1))

            locations_list = []
            not_pushed_count = 0
            for location in locations:
                if location.name not in existing_locations:
                    locations_list.append(json.dumps({
                        'name': location.name
                    }))
                else:
                    not_pushed_count += 1

            logger.info(f"{not_pushed_count} locations already in queue, not pushed again.")

        if locations_list:
            await redis_conn.rpush('locations_without_geocoding_queue', *locations_list)
            logger.info(f"Pushed {len(locations_list)} locations to Redis queue.")
        else:
            logger.info("No new locations found that need geocoding.")

        await redis_conn.close()
        return {"message": f"Geocoding jobs created for {len(locations_list)} locations."}
    except Exception as e:
        logger.error(f"Error creating geocoding jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/store_contents_with_geocoding")
async def store_contents_with_geocoding(session: AsyncSession = Depends(get_session)):
    try:
        logger.info("Starting store_contents_with_geocoding function")
        redis_conn = await Redis.from_url(get_redis_url(), db=4, decode_responses=True)
        geocoded_contents = await redis_conn.lrange('contents_with_geocoding_queue', 0, -1)
        logger.info(f"Retrieved {len(geocoded_contents)} geocoded locations from Redis queue")
        
        async with session.begin():
            for index, geocoded_content in enumerate(geocoded_contents, 1):
                try:
                    geocode_data = json.loads(geocoded_content)
                    location_name = geocode_data['name']
                    
                    # Update or create the Location entry
                    stmt = select(Location).where(Location.name == location_name)
                    result = await session.execute(stmt)
                    location = result.scalar_one_or_none()

                    if not location:
                        location = Location(
                            name=location_name,
                            location_type=geocode_data.get('type', 'unknown'),
                            coordinates=geocode_data.get('coordinates'),
                            bbox=geocode_data.get('bbox'),
                            area=geocode_data.get('area'),
                            weight=geocode_data.get('weight', 1.0)
                        )
                        session.add(location)
                        logger.info(f"Added new location: {location_name}")
                    else:
                        # Update existing location details if necessary
                        location.coordinates = geocode_data.get('coordinates', location.coordinates)
                        # location.bbox = geocode_data.get('bbox', location.bbox)
                        # location.area = geocode_data.get('area', location.area)
                        location.weight = max(location.weight, geocode_data.get('weight', location.weight))
                        logger.info(f"Updated location: {location_name}")

                except Exception as e:
                    logger.error(f"Error processing geocoded location {geocode_data.get('name', 'unknown')}: {e}", exc_info=True)

        await session.commit()
        logger.info("Stored geocoded locations in PostgreSQL")

        # Clear the processed geocoded contents from Redis
        await redis_conn.ltrim('contents_with_geocoding_queue', len(geocoded_contents), -1)
        await redis_conn.close()
        return {"message": "Geocoded locations stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing geocoded locations: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        await session.close()

########################################################################################
## 5. LLM CLASSIFICATION PIPELINE

@router.post("/create_classification_jobs")
async def create_classification_jobs(session: AsyncSession = Depends(get_session)):
    logger.info("Starting to create classification jobs.")
    try:
        async with session.begin():
            # Select contents with no evaluati
            query = select(Content).where(Content.evaluation == None)
            result = await session.execute(query)
            contents = result.scalars().all()
            logger.info(f"Found {len(contents)} contents with no classification.")

            redis_conn = await Redis.from_url(get_redis_url(), db=4)
            existing_urls = set(await redis_conn.lrange('contents_without_classification_queue', 0, -1))
            existing_urls = {json.loads(url)['url'] for url in existing_urls}

            contents_list = []
            not_pushed_count = 0
            for content in contents:
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
            await redis_conn.rpush('contents_without_classification_queue', *contents_list)
            logger.info(f"Pushed {len(contents_list)} contents to Redis queue for classification.")
        else:
            logger.info("No new contents found for classification.")
        await redis_conn.close()
        return {"message": f"Classification jobs created for {len(contents_list)} contents."}
    except Exception as e:
        logger.error(f"Error creating classification jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/store_contents_with_classification")
async def store_contents_with_classification(session: AsyncSession = Depends(get_session)):
    try:
        logger.info("Starting store_contents_with_classification function")
        redis_conn = await Redis.from_url(get_redis_url(), db=4, decode_responses=True)
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
                    # if not existing, insert new content
                    content = Content(**content_data)
                    session.add(content)
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











