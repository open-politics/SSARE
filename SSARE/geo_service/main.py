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
from prefect_ray import RayTaskRunner

from core.service_mapping import ServiceConfig
from core.models import Article, Entity, Location
from core.db import get_session

config = ServiceConfig()

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@task
def retrieve_articles_from_redis(redis_conn, batch_size=50):
    batch = redis_conn.lrange('articles_without_geocoding_queue', 0, batch_size - 1)
    redis_conn.ltrim('articles_without_geocoding_queue', batch_size, -1)
    return [json.loads(article) for article in batch]

@task
def call_pelias_api(location, lang=None):
    try:
        pelias_url = config.service_urls['pelias_placeholder']
        url = f"{pelias_url}/parser/search?text={location}"
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

@task
def process_article(article_data):
    entities = article_data.get('entities', [])
    location_entities = [entity for entity in entities if entity['entity_type'] in ["GPE", "LOC"]]
    location_counts = Counter(entity['name'] for entity in location_entities)
    total_locations = len(location_entities)
    location_weights = {location: count / total_locations for location, count in location_counts.items()}

    geocoded_locations = []
    for location, weight in location_weights.items():
        coordinates = call_pelias_api(location, lang='en')
        if coordinates:
            geocoded_locations.append({
                'name': location,
                'type': "GPE",
                'coordinates': coordinates
            })
            logger.info(f"Geocoded location {location} with coordinates {coordinates}.")
        else:
            logger.warning(f"Unable to geocode location: {location}")

    return {**article_data, 'geocoded_locations': geocoded_locations}

@task
def push_geocoded_articles(redis_conn, geocoded_articles):
    for article in geocoded_articles:
        redis_conn.lpush('articles_with_geocoding_queue', json.dumps(article))
    logger.info(f"Pushed {len(geocoded_articles)} geocoded articles to Redis queue.")

@flow(task_runner=RayTaskRunner())
def geocode_articles_flow(batch_size: int):
    logger.info("Starting geocoding process")
    redis_conn_raw = Redis(host='redis', port=6379, db=3, decode_responses=True)
    redis_conn_processed = Redis(host='redis', port=6379, db=4, decode_responses=True)

    try:
        raw_articles = retrieve_articles_from_redis(redis_conn_raw, batch_size)
        geocoded_articles = [process_article(article) for article in raw_articles]
        push_geocoded_articles(redis_conn_processed, geocoded_articles)
    finally:
        redis_conn_raw.close()
        redis_conn_processed.close()

    logger.info("Geocoding process completed")

@app.post("/geocode_articles")
def geocode_articles(batch_size: int = 50):
    logger.info("GEOCODING ARTICLES")
    geocode_articles_flow(batch_size)
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