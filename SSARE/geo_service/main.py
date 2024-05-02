import os
import pandas as pd
import ast
import json
from geopy.geocoders import Nominatim
from fastapi import FastAPI, HTTPException
from pydantic import Base
import logging
from prefect import task, flow, get_run_logger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

@app.get("/healthz")
async def healthcheck():
    return {"message": "NLP Service Running"}, 200


logging
# Load the dataset
@task
async def retrieve_articles_from_redis(redis_conn_raw):
    logger = get_run_logger()
    raw_articles_json = await redis_conn_raw.lrange('articles_without_embedding_queue', 0, -1)
    logger.info(f"Retrieved {len(raw_articles_json)} articles from Redis")
    return raw_articles_json

# Initialize the dictionary to hold location-article mappings
location_articles = {}

# Initialize geocoder
geolocator = Nominatim(user_agent="geoapiExercises")

# Process each row in the DataFrame
# Process each row in the DataFrame
for index, row in df.iterrows():
    entity_list = ast.literal_eval(row['entities'])
    print(entity_list) # Moved the print statement here
    gpe_instances = list(set([entity[0] for entity in entity_list if entity[1] == 'GPE']))

    # Add the article and URL to the list for each location mentioned
    for location in gpe_instances:
        if location not in location_articles:
            location_articles[location] = []
        location_articles[location].append({
            'headline': row['headline'],
            'url': row['url']
        })

# Prepare the geojson structure
geojson = {
    "type": "FeatureCollection",
    "features": []
}

# Populate the geojson structure
for location, articles in location_articles.items():
    try:
        location_geo = geolocator.geocode(location)
        if location_geo:
            feature = {
                "type": "Feature",
                "properties": {
                    "location": location,
                    "articles": articles
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [location_geo.longitude, location_geo.latitude]
                }
            }
            geojson['features'].append(feature)
    except Exception as e:
        print(f"Error geocoding {location}: {e}")

# Ensure the directory exists
geo_data_dir = '/Users/jimvincentwagner/pol/open-politics/open_politics_project/news/static/geo_data'
if not os.path.exists(geo_data_dir):
    os.makedirs(geo_data_dir)

# Save the geojson to a file
with open(os.path.join(geo_data_dir, 'articles.geojson'), 'w') as f:
    json.dump(geojson, f)

print("GeoJSON file created successfully.")
