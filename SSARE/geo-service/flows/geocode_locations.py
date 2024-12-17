import json
import logging
from typing import List, Dict, Any
from redis import Redis
from core.utils import UUIDEncoder, get_redis_url
from prefect import task, flow
from collections import Counter
import requests
from core.service_mapping import config
import os

from logging import basicConfig, getLogger

import logfire

logfire.configure()
basicConfig(handlers=[logfire.LogfireLoggingHandler()])

logger = getLogger(__name__)

# Helper function to get Redis cache connection
def get_redis_cache():
    return Redis.from_url(get_redis_url(), db=5)  # Using db 5 for caching

# Function to retrieve contents from Redis
def retrieve_contents_from_redis(batch_size: int) -> List[Dict[str, Any]]:
    redis_conn = Redis.from_url(get_redis_url(), db=3, decode_responses=True)
    try:
        batch = redis_conn.lrange('contents_without_geocoding_queue', 0, batch_size - 1)
        redis_conn.ltrim('contents_without_geocoding_queue', batch_size, -1)
        
        # Deserialize JSON strings to dictionaries
        contents = [json.loads(content_json) for content_json in batch]
        
        return contents
    finally:
        redis_conn.close()

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
        print(os.getenv('PELIAS_PLACEHOLDER_PORT'))
        pelias_url = config.service_urls['pelias-placeholder']
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
                    looger.warning(f"No geometry found for location: {location}")

            else:
                logger.warning(f"No data returned from API for location: {location}")
        else:
            logger.error(f"API call failed with status code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"API call exception for location {location}: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error for location {location}: {str(e)}")
    return None

# Function to process individual location and geocode
def process_location(location: Dict[str, Any]) -> Dict[str, Any]:
    location_name = location.get('name')
    if not location_name:
        logger.warning("No location name provided.")
        return {}

    geocode_result = call_pelias_api(location_name, lang='en')

    if geocode_result:
        geocode_result['name'] = location_name
        geocode_result['type'] = geocode_result.get('location_type', 'unknown')
        logger.info(f"Geocoded location {location_name}: {geocode_result}")
        return geocode_result
    else:
        logger.warning(f"Unable to geocode location: {location_name}")
        redis_conn = Redis.from_url(get_redis_url(), db=6)
        redis_conn.lpush('failed_geocodes_queue', json.dumps({'name': location_name}))
        return {'name': location_name, 'error': 'Geocoding failed'}

# Function to push geocoded contents to Redis
@task(log_prints=True)
def push_geocoded_contents(contents_with_geocoding: List[Dict[str, Any]]):
    redis_conn = Redis.from_url(get_redis_url(), db=4, decode_responses=True)
    try:
        for content in contents_with_geocoding:
            redis_conn.lpush('contents_with_geocoding_queue', json.dumps(content, cls=UUIDEncoder))
            logger.info(f"Content with geocoding pushed to queue: {content}")
    except Exception as e:
        logger.error(f"Error pushing contents with geocoding to queue: {str(e)}")
    finally:
        redis_conn.close()

# Function to handle failed geocoding attempts
def handle_failed_geocodes(failed_locations: List[str]):
    redis_conn = Redis.from_url(get_redis_url(), db=6)  # Using db 6 for failed geocodes
    try:
        for loc in failed_locations:
            redis_conn.lpush('failed_geocodes_queue', json.dumps({'name': loc}))
            logger.info(f"Failed to geocode location pushed to queue: {loc}")
    except Exception as e:
        logger.error(f"Error pushing failed geocodes to queue: {e}")
    finally:
        redis_conn.close()

@flow
def geocode_locations_flow(batch_size: int = 100):
    logger.info("Starting geocoding process for locations")
    redis_conn = Redis.from_url(get_redis_url(), db=3, decode_responses=True)
    try:
        locations_batch = redis_conn.lrange('locations_without_geocoding_queue', 0, batch_size - 1)
        redis_conn.ltrim('locations_without_geocoding_queue', batch_size, -1)

        locations = [json.loads(loc) for loc in locations_batch]
        if not locations:
            logger.info("No locations found in the queue.")
            return {"message": "No locations to process."}

        geocoded_locations = []
        failed_geocodes = []

        for loc in locations:
            result = process_location(loc)
            if 'error' in result:
                failed_geocodes.append(result['name'])
            else:
                geocoded_locations.append(result)

        # Push successful geocodes to the next queue
        if geocoded_locations:
            push_geocoded_contents(geocoded_locations)

        # Optionally, handle failed geocodes
        if failed_geocodes:
            handle_failed_geocodes(failed_geocodes)

        logger.info(f"Geocoding completed for {len(geocoded_locations)} locations.")
        return {"message": f"Geocoding completed for {len(geocoded_locations)} locations.", "failed": len(failed_geocodes)}
    finally:
        redis_conn.close()
        logger.info("Geocoding process completed.")

if __name__ == "__main__":
    geocode_locations_flow.serve(
        name="geocode-locations-deployment",
        cron="*/6 * * * *",
        parameters={"batch_size": 50}
    )
