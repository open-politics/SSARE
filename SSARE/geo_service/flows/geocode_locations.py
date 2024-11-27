import json
import logging
from typing import List, Dict, Any
from redis import Redis
from core.utils import logger, UUIDEncoder, get_redis_url
from prefect import task, flow
from collections import Counter
import requests
from core.service_mapping import config

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
def process_content(content: Dict[str, Any]) -> Dict[str, Any]:
    entities = content.get('entities', [])
    # Filter entities where tag is "LOC"
    location_entities = [entity for entity in entities if entity.get('tag') == "LOC"]
    
    logger.warning(f"Location entities: {location_entities}")
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

    # Attach geocoded locations to the content dictionary
    content['geocoded_locations'] = geocoded_locations
    return content

# Function to push geocoded contents to Redis
@task(log_prints=True)
def push_geocoded_contents(contents_with_geocoding: List[Dict[str, Any]]):
    redis_conn = Redis.from_url(get_redis_url(), db=4, decode_responses=True)
    try:
        for content in contents_with_geocoding:
            redis_conn.lpush('contents_with_geocoding_queue', json.dumps(content, cls=UUIDEncoder))
            logger.info(f"Content with geocoding pushed to queue: {content['url']}")
    except Exception as e:
        logger.error(f"Error pushing contents with geocoding to queue: {str(e)}")
    finally:
        redis_conn.close()

@flow
def geocode_locations_flow(batch_size: int = 50):
    logger.info("Starting geocoding process")
    contents = retrieve_contents_from_redis(batch_size)
    if contents:
        contents_with_geocoding = []
        for content in contents:
            processed_content = process_content(content)
            if processed_content:
                contents_with_geocoding.append(processed_content)
        push_geocoded_contents(contents_with_geocoding)
        logger.info(f"Geocoding completed for {len(contents_with_geocoding)} contents.")
    else:
        logger.info("No contents found in the queue.")
    logger.info("Geocoding process completed")
    return {"message": "Geocoding completed"}

if __name__ == "__main__":
    geocode_locations_flow.serve(
        name="geocode-locations-deployment",
        cron="*/6 * * * *",
        parameters={"batch_size": 50}
    )
