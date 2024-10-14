# geocoding_service.py

from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends
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
from core.models import (
    Content, ContentEntity, Entity, EntityLocation, Location, ContentClassification
)
from core.adb import get_session

config = ServiceConfig()

async def lifespan(app):
    logger.warning("Starting lifespan")
    yield

app = FastAPI(lifespan=lifespan)

@task
def retrieve_contents_from_redis(redis_conn, batch_size=50):
    batch = redis_conn.lrange('contents_without_geocoding_queue', 0, batch_size - 1)
    redis_conn.ltrim('contents_without_geocoding_queue', batch_size, -1)
    return [json.loads(content) for content in batch]

@task
def call_pelias_api(location_name, lang=None):
    try:
        pelias_url = config.service_urls['pelias_placeholder']
        url = f"{pelias_url}/parser/search?text={location_name}"
        if lang:
            url += f"&lang={lang}"

        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                item_0 = data[0]
                geometry = item_0.get('geom')
                if geometry:
                    return [geometry.get('lon'), geometry.get('lat')]
                else:
                    logger.warning(f"No geometry found for location: {location_name}")
            else:
                logger.warning(f"No data returned from API for location: {location_name}")
        else:
            logger.error(f"API call failed with status code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"API call exception for location {location_name}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error for location {location_name}: {str(e)}")
    return None

@task
def process_content(content_data):
    entities = content_data.get('entities', [])
    location_entities = [entity for entity in entities if entity['entity_type'] in ["GPE", "LOC"]]
    location_counts = Counter(entity['name'] for entity in location_entities)
    total_locations = len(location_entities)
    location_weights = {location: count / total_locations for location, count in location_counts.items()}

    geocoded_locations = []
    for location_name, weight in location_weights.items():
        coordinates = call_pelias_api(location_name, lang='en')
        if coordinates:
            # Confidence threshold
            if weight > 0.05:  # Only including locations that appear in more than 5% of entities
                geocoded_locations.append({
                    'name': location_name,
                    'type': "GPE",
                    'coordinates': coordinates,
                    'weight': weight
                })
                logger.info(f"Geocoded location {location_name} with coordinates {coordinates} and weight {weight}.")
            else:
                logger.info(f"Skipped low-weight location: {location_name} (weight: {weight})")
        else:
            logger.warning(f"Unable to geocode location: {location_name}")

    return {**content_data, 'geocoded_locations': geocoded_locations}

@task
def push_geocoded_contents(redis_conn, geocoded_contents):
    for content in geocoded_contents:
        redis_conn.lpush('contents_with_geocoding_queue', json.dumps(content))
    logger.info(f"Pushed {len(geocoded_contents)} geocoded contents to Redis queue.")

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

@app.post("/geocode_contents")
def geocode_contents(batch_size: int = 50):
    logger.info("GEOCODING CONTENTS")
    geocode_contents_flow(batch_size)
    return {"message": "Geocoding process initiated successfully"}

@app.get("/healthz")
def healthcheck():
    return {"message": "ok"}, 200

@app.get("/geojson")
async def get_locations_geojson(session: AsyncSession = Depends(get_session)):
    logger.info("Starting GeoJSON generation")
    try:
        # Query to get all locations with their associated entities and contents
        logger.debug("Querying database for locations, entities, and contents")
        query = select(Location).options(
            selectinload(Location.entities).selectinload(Entity.contents)
        )
        result = await session.execute(query)
        locations = result.scalars().unique().all()
        logger.info(f"Retrieved {len(locations)} locations from database")

        features = []
        for location in locations:
            logger.debug(f"Processing location: {location.name}")
            # Convert coordinates to regular Python floats
            coordinates = [float(coord) for coord in location.coordinates]
            # Create a Point geometry
            point = Point((coordinates[1], coordinates[0]))  # GeoJSON uses (longitude, latitude)

            # Collect all contents associated with this location
            contents = []
            for entity in location.entities:
                for content in entity.contents:
                    contents.append({
                        "url": content.url,
                        "title": content.title,
                        "source": content.source,
                        "insertion_date": content.insertion_date.isoformat() if content.insertion_date else None
                    })
            logger.debug(f"Found {len(contents)} contents for location: {location.name}")

            # Create a Feature
            feature = Feature(
                geometry=point,
                properties={
                    "name": location.name,
                    "type": location.type,
                    "content_count": len(contents),
                    "contents": contents
                }
            )
            features.append(feature)

        # Create a FeatureCollection
        feature_collection = FeatureCollection(features)
        logger.info(f"Created FeatureCollection with {len(features)} features")

        logger.info("GeoJSON generation completed successfully")
        return JSONResponse(content=feature_collection)

    except Exception as e:
        logger.error(f"Error creating GeoJSON: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/geojson_events/{event_type}")
async def get_geojson_by_event_type(event_type: str, session: AsyncSession = Depends(get_session)):
    logger.info(f"Starting GeoJSON generation for event type: {event_type}")
    try:
        # Query to get all locations with their associated entities and contents filtered by event type
        logger.debug("Querying database for locations, entities, and contents")
        query = (
            select(Location)
            .options(selectinload(Location.entities).selectinload(Entity.contents))
            .join(EntityLocation, EntityLocation.location_id == Location.id)
            .join(Entity, Entity.id == EntityLocation.entity_id)
            .join(ContentEntity, ContentEntity.entity_id == Entity.id)
            .join(Content, Content.id == ContentEntity.content_id)
            .join(ContentClassification, ContentClassification.content_id == Content.id)
            .where(ContentClassification.event_type == event_type)
        )
        result = await session.execute(query)
        locations = result.scalars().unique().all()
        logger.info(f"Retrieved {len(locations)} locations from database for event type: {event_type}")

        features = []
        for location in locations:
            logger.debug(f"Processing location: {location.name}")
            # Convert coordinates to regular Python floats
            coordinates = [float(coord) for coord in location.coordinates]
            # Create a Point geometry
            point = Point((coordinates[1], coordinates[0]))  # GeoJSON uses (longitude, latitude)

            # Collect all contents associated with this location
            contents = []
            for entity in location.entities:
                for content in entity.contents:
                    contents.append({
                        "url": content.url,
                        "title": content.title,
                        "source": content.source,
                        "insertion_date": content.insertion_date.isoformat() if content.insertion_date else None
                    })
            logger.debug(f"Found {len(contents)} contents for location: {location.name}")

            # Create a Feature
            feature = Feature(
                geometry=point,
                properties={
                    "name": location.name,
                    "type": location.type,
                    "content_count": len(contents),
                    "contents": contents
                }
            )
            features.append(feature)

        # Create a FeatureCollection
        feature_collection = FeatureCollection(features)
        logger.info(f"Created FeatureCollection with {len(features)} features for event type: {event_type}")

        logger.info("GeoJSON generation completed successfully")
        return JSONResponse(content=feature_collection)

    except Exception as e:
        logger.error(f"Error creating GeoJSON for event type {event_type}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
