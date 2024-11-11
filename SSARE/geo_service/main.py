from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
from redis import Redis
import logging
from collections import Counter
import requests
from prefect import task, flow
from geojson import Feature, FeatureCollection, Point
from fastapi.responses import JSONResponse
from sqlalchemy.orm import selectinload
from sqlalchemy import and_
from core.utils import logger
from core.service_mapping import ServiceConfig
from core.models import Content, Location, Entity, ContentEvaluation, EntityLocation, ContentEntity
from core.adb import get_session
import uuid
import pickle
from datetime import timedelta
import asyncio
from datetime import datetime

config = ServiceConfig()

import sys

# Constants for Redis cache configuration
REDIS_CACHE_HOST = 'redis'
REDIS_CACHE_PORT = 6379
REDIS_CACHE_DB = 5  # Using a different DB for caching
CACHE_EXPIRY = timedelta(minutes=15)  # Cache for 15 minutes

# Add these constants
CACHE_WARM_INTERVAL = timedelta(minutes=14)  # Slightly less than cache expiry
LAST_WARM_KEY = "geojson_last_warm"

# Helper function to get Redis cache connection
def get_redis_cache():
    return Redis(
        host=REDIS_CACHE_HOST,
        port=REDIS_CACHE_PORT,
        db=REDIS_CACHE_DB
    )

# Add cache warming function
async def warm_cache(session: AsyncSession):
    logger.info("Starting cache warm-up")
    redis_cache = get_redis_cache()
    
    try:
        # Generate and cache main GeoJSON
        feature_collection = await generate_geojson(session)
        redis_cache.setex(
            "geojson_all",
            CACHE_EXPIRY,
            pickle.dumps(feature_collection)
        )
        
        # Generate and cache common event types
        event_types = ["protest", "conflict", "disaster"]
        for event_type in event_types:
            feature_collection = await generate_event_geojson(session, event_type)
            redis_cache.setex(
                f"geojson_events_{event_type}",
                CACHE_EXPIRY,
                pickle.dumps(feature_collection)
            )
        
        redis_cache.set(LAST_WARM_KEY, datetime.utcnow().isoformat())
        logger.info("Cache warm-up completed")
        
    except Exception as e:
        logger.error(f"Error during cache warm-up: {e}")
        raise
    finally:
        redis_cache.close()

# Modify the lifespan function
async def lifespan(app: FastAPI):
    logger.warning("Starting lifespan")
    
    # Start background cache warming task
    async def periodic_cache_warm():
        while True:
            try:
                # Create a new session for each warm-up cycle
                async for session in get_session():
                    try:
                        await warm_cache(session)
                    except Exception as e:
                        logger.error(f"Error during cache warm-up: {e}")
                await asyncio.sleep(CACHE_WARM_INTERVAL.total_seconds())
            except Exception as e:
                logger.error(f"Error in periodic cache warming: {e}")
                await asyncio.sleep(60)  # Wait a minute before retrying
    
    # Start the background task
    asyncio.create_task(periodic_cache_warm())
    
    yield

app = FastAPI(lifespan=lifespan)

# Function to retrieve contents from Redis
def retrieve_contents_from_redis(redis_conn, batch_size=50):
    batch = redis_conn.lrange('contents_without_geocoding_queue', 0, batch_size - 1)
    redis_conn.ltrim('contents_without_geocoding_queue', batch_size, -1)
    return [json.loads(content) for content in batch]

# Function to call Pelias API for geocoding
def call_pelias_api(location, lang=None):
    custom_mappings = {
        "europe": {
            'coordinates': [13.405, 52.52],
            'location_type': 'continent',
            'bbox': [-24.539906, 34.815009, 69.033946, 81.85871],
            'area': 1433.861436
        },
    }

    if location.lower() in custom_mappings:
        return custom_mappings[location.lower()]

    try:
        pelias_url = config.service_urls['pelias_placeholder']
        url = f"{pelias_url}/parser/search?text={location}"
        if lang:
            url += f"&lang={lang}"

        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                top_result = data[0]
                geometry = top_result.get('geom')
                location_type = top_result.get('placetype', 'location')
                if geometry:
                    bbox = geometry.get('bbox')
                    area = geometry.get('area')
                    return {
                        'coordinates': [geometry.get('lon'), geometry.get('lat')],
                        'location_type': location_type if location_type else 'location',
                        'bbox': bbox.split(',') if bbox else None,
                        'area': area
                    }
                else:
                    logger.warning(f"No geometry found for location: {location}")
            else:
                logger.warning(f"No data returned from API for location: {location}")
        else:
            logger.error(f"API call failed with status code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"API call exception for location {location}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error for location {location}: {str(e)}")
    return None

# Function to process content and geocode locations
def process_content(content_data):
    entities = content_data.get('entities', [])
    location_entities = [entity for entity in entities if entity['tag'] in ["location", "facility"]]
    location_counts = Counter(entity['text'] for entity in location_entities)
    total_locations = len(location_entities)
    location_weights = {location: count / total_locations for location, count in location_counts.items()}

    geocoded_locations = []
    for location, weight in location_weights.items():
        coordinates = call_pelias_api(location, lang='en')
        if coordinates:
            if weight > 0.03:
                geocoded_locations.append({
                    'name': location,
                    'type': "location",
                    'coordinates': coordinates,
                    'weight': weight
                })
                logger.info(f"Geocoded location {location} with coordinates {coordinates} and weight {weight}.")
            else:
                logger.info(f"Skipped low-weight location: {location} (weight: {weight})")
        else:
            logger.warning(f"Unable to geocode location: {location}")

    return {**content_data, 'geocoded_locations': geocoded_locations}

# Function to push geocoded contents to Redis
@task
def push_geocoded_contents(redis_conn, geocoded_contents):
    for content in geocoded_contents:
        redis_conn.lpush('contents_with_geocoding_queue', json.dumps(content))
    logger.info(f"Pushed {len(geocoded_contents)} geocoded contents to Redis queue.")

# Flow to geocode contents
@flow
def geocode_contents_flow(batch_size: int):
    logger.info("Starting geocoding process")
    redis_conn_raw = Redis(host='redis', port=6379, db=3, decode_responses=True)
    redis_conn_processed = Redis(host='redis', port=6379, db=4, decode_responses=True)

    try:
        raw_contents = retrieve_contents_from_redis(redis_conn_raw, batch_size)
        geocoded_contents = [process_content(content) for content in raw_contents]
        push_geocoded_contents(redis_conn_processed, geocoded_contents)
    finally:
        redis_conn_raw.close()
        redis_conn_processed.close()

    logger.info("Geocoding process completed")

@app.get("/geocode_location")
def geocode_location(location: str):
    logger.info(f"Geocoding location: {location}")
    coordinates = call_pelias_api(location, lang='en')
    logger.warning(f"Coordinates: {coordinates}")

    if coordinates:
        return {
            "coordinates": coordinates['coordinates'],
            "location_type": coordinates['location_type'],
            "bbox": coordinates.get('bbox'),
            "area": coordinates.get('area')
        }
    else:
        return {"error": "Unable to geocode location"}

@app.post("/geocode_contents")
def geocode_contents(batch_size: int = 50):
    logger.info("GEOCODING CONTENTS")
    geocode_contents_flow(batch_size)
    return {"message": "Geocoding process initiated successfully"}

@app.get("/get_country_data")
def get_country_data(country):
    url = f"https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": country,
        "prop": "extracts",
        "exintro": True,
        "explaintext": True
    }
    response = requests.get(url, params=params)
    data = response.json()
    pages = data['query']['pages']
    for page_id, page_data in pages.items():
        if 'extract' in page_data:
            return page_data['extract']
    return None

@app.get("/healthz")
def healthcheck():
    return {"message": "ok"}, 200

# Task to log GeoJSON generation
@task
async def logging_geojson(position):
    logger.info("Starting GeoJSON generation")
    print(f"GeoJSON {position} ")

# Get all locations GeoJSON
@app.get("/geojson")
async def get_locations_geojson(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
):
    redis_cache = get_redis_cache()
    cache_key = "geojson_all"
    
    try:
        cached_data = redis_cache.get(cache_key)
        if cached_data:
            # Check if cache is getting stale
            last_warm = redis_cache.get(LAST_WARM_KEY)
            if last_warm:
                last_warm_time = datetime.fromisoformat(last_warm.decode())
                if datetime.utcnow() - last_warm_time > CACHE_WARM_INTERVAL:
                    background_tasks.add_task(warm_cache, session)
            
            logger.info("Returning GeoJSON from cache")
            return JSONResponse(content=pickle.loads(cached_data))
        
        # If no cache exists, generate and cache
        feature_collection = await generate_geojson(session)
        redis_cache.setex(
            cache_key,
            CACHE_EXPIRY,
            pickle.dumps(feature_collection)
        )
        
        return JSONResponse(content=feature_collection)
        
    except Exception as e:
        logger.error(f"Error in GeoJSON generation/caching: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        redis_cache.close()

# Get event-specific GeoJSON
@app.get("/geojson_events/{event_type}")
async def get_geojson_by_event_type(event_type: str, session: AsyncSession = Depends(get_session)):
    redis_cache = get_redis_cache()
    cache_key = f"geojson_events_{event_type}"
    
    try:
        cached_data = redis_cache.get(cache_key)
        if cached_data:
            logger.info(f"Returning {event_type} GeoJSON from cache")
            return JSONResponse(content=pickle.loads(cached_data))
            
        feature_collection = await generate_event_geojson(session, event_type)
        
        redis_cache.setex(
            cache_key,
            CACHE_EXPIRY,
            pickle.dumps(feature_collection)
        )
        
        return JSONResponse(content=feature_collection)
        
    except Exception as e:
        logger.error(f"Error in event GeoJSON generation/caching: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        redis_cache.close()

@app.post("/geojson_by_content_ids")
async def get_geojson_by_content_ids(
    content_ids: List[str],
    session: AsyncSession = Depends(get_session)
):
    logger.warning("Starting GeoJSON generation for specified content IDs")
    logger.warning(f"Content IDs: {content_ids}")
    try:
        content_uuids = [uuid.UUID(content_id) for content_id in content_ids]

        query = (
            select(Content)
            .options(selectinload(Content.entities).selectinload(Entity.locations))
            .where(Content.id.in_(content_uuids))
        )

        result = await session.execute(query)
        contents = result.scalars().unique().all()
        logger.warning(f"Retrieved {len(contents)} contents from database")

        features = []
        for content in contents:
            for entity in content.entities:
                for location in entity.locations:
                    logger.debug(f"Processing location: {location.name}")
                    coordinates = [float(coord) for coord in location.coordinates]
                    point = Point((coordinates[1], coordinates[0]))

                    feature = Feature(
                        geometry=point,
                        properties={
                            "content_id": str(content.id),
                            "url": content.url,
                            "title": content.title,
                            "source": content.source,
                            "insertion_date": content.insertion_date,
                            "location_name": location.name,
                            "location_type": location.location_type
                        }
                    )
                    features.append(feature)

        feature_collection = FeatureCollection(features)
        logger.warning(f"Created FeatureCollection with {len(features)} features for specified contents")
        return JSONResponse(content=feature_collection)

    except Exception as e:
        logger.error(f"Error creating GeoJSON for specified contents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Helper function to generate GeoJSON
async def generate_geojson(session: AsyncSession) -> dict:
    query = select(Location).options(
        selectinload(Location.entities).selectinload(Entity.contents)
    )
    result = await session.execute(query)
    locations = result.scalars().unique().all()
    
    features = []
    for location in locations:
        logger.debug(f"Processing location: {location.name}")
        coordinates = [float(coord) for coord in location.coordinates]
        point = Point((coordinates[1], coordinates[0]))

        contents = []
        for entity in location.entities:
            for content in entity.contents:
                contents.append({
                    "url": content.url,
                    "title": content.title,
                    "source": content.source,
                    "insertion_date": content.insertion_date
                })
        logger.debug(f"Found {len(contents)} contents for location: {location.name}")

        feature = Feature(
            geometry=point,
            properties={
                "name": location.name,
                "type": location.location_type,
                "content_count": len(contents),
                "contents": contents
            }
        )
        features.append(feature)

    feature_collection = FeatureCollection(features)
    logger.info(f"Created FeatureCollection with {len(features)} features")

    logger.info("GeoJSON generation completed successfully")
    await logging_geojson("generation completed")
    return feature_collection

# Helper function to generate event-specific GeoJSON
async def generate_event_geojson(session: AsyncSession, event_type: str) -> dict:
    query = (
        select(Location)
        .options(selectinload(Location.entities).selectinload(Entity.contents))
        .join(EntityLocation, EntityLocation.location_id == Location.id)
        .join(Entity, Entity.id == EntityLocation.entity_id)
        .join(ContentEntity, ContentEntity.entity_id == Entity.id)
        .join(Content, Content.id == ContentEntity.content_id)
        .join(ContentEvaluation, ContentEvaluation.content_id == Content.id)
        .where(ContentEvaluation.event_type == event_type)
    )
    result = await session.execute(query)
    locations = result.scalars().unique().all()
    logger.info(f"Retrieved {len(locations)} locations from database for event type: {event_type}")

    features = []
    for location in locations:
        logger.debug(f"Processing location: {location.name}")
        coordinates = [float(coord) for coord in location.coordinates]
        point = Point((coordinates[1], coordinates[0]))

        contents = []
        for entity in location.entities:
            for content in entity.contents:
                contents.append({
                    "url": content.url,
                    "title": content.title,
                    "source": content.source,
                    "insertion_date": content.insertion_date
                })
        logger.debug(f"Found {len(contents)} contents for location: {location.name}")

        feature = Feature(
            geometry=point,
            properties={
                "name": location.name,
                "type": location.location_type,
                "content_count": len(contents),
                "contents": contents
            }
        )
        features.append(feature)

    feature_collection = FeatureCollection(features)
    logger.info(f"Created FeatureCollection with {len(features)} features for event type: {event_type}")
    await logging_geojson("events generation completed")

    logger.info("GeoJSON generation completed successfully")
    return feature_collection

