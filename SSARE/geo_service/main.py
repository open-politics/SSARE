from typing import List, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select
import json
from redis.asyncio import Redis
import logging
from collections import Counter
import requests

from core.service_mapping import ServiceConfig
from core.models import Article, Entity, Location, ArticleEntity
from core.db import engine, get_session

config = ServiceConfig()

app = FastAPI()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Article.metadata.create_all)

# Geocoding endpoint
@app.post("/geocode_articles")
async def geocode_articles():
    redis_conn_input = await Redis(host='redis', port=6379, db=3)
    redis_conn_output = await Redis(host='redis', port=6379, db=4)
    try:
        article_data_json = await redis_conn_input.rpop('articles_without_geocoding_queue')

        if not article_data_json:
            return {"message": "No articles available for geocoding."}

        logger.info(f"Processing article: {article_data_json}")
        article_data = json.loads(article_data_json)
        entities = article_data.get('entities', [])

        if not entities:
            return {"message": "No valid entities available for geocoding."}

        location_entities = [entity for entity in entities if entity['entity_type'] == "GPE"]
        logger.info(f"Found {len(location_entities)} GPE entities")
        location_counts = Counter(entity['name'] for entity in location_entities)
        total_locations = len(location_entities)
        location_weights = {location: count / total_locations for location, count in location_counts.items()}

        geocoded_locations = []
        for location, weight in location_weights.items():
            coordinates = call_pelias_api(location, lang='en')
            if coordinates:
                geocoded_locations.append({
                    "name": location,
                    "type": "GPE",
                    "coordinates": coordinates
                })
                logger.info(f"Geocoded location {location} with coordinates {coordinates}.")
            else:
                logger.warning(f"Unable to geocode location {location}: No coordinates found.")

        # Prepare the geocoded data
        geocoded_data = {
            "url": article_data['url'],
            "geocoded_locations": geocoded_locations
        }

        # Push the geocoded data to the new Redis queue
        await redis_conn_output.lpush('articles_with_geocoding_queue', json.dumps(geocoded_data))
        logger.info(f"Pushed geocoded data for article {article_data['url']} to Redis queue")

        return {"message": "Article geocoded and pushed to queue successfully"}
    except Exception as e:
        logger.error(f"Error processing article for geocoding: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await redis_conn_input.close()
        await redis_conn_output.close()

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

@app.get("/call_pelias_api")
def call_pelias_api(location, lang=None, placetype=None):
    try:
        # Use the pelias_placeholder URL from service_urls
        pelias_url = config.service_urls['pelias_placeholder']
        url = f"{pelias_url}/parser/search?text={location}"
        if lang:
            url += f"&lang={lang}"

        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            item_0 = data[0]
            geometry = item_0['geom']
            lat = geometry['lat']
            lon = geometry['lon']
            coordinates = [lon, lat]
            return coordinates
        else:
            logger.error(f"API call failed with status code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"API call exception for location {location}: {str(e)}")
    return None

# Kubernetes endpoint
@app.get("/healthz")
def test_endpoint():
    return {"message": "ok"}, 200
