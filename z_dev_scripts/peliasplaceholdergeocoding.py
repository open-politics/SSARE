import requests
import logging

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def call_pelias_api(location, lang=None, placetype=None):
    try:
        # Construct the API URL with optional language and placetype parameters
        url = f"http://136.243.80.175:3000/parser/query?text={location}"
        if lang:
            url += f"&lang={lang}"
        if placetype:
            url += f"&placetype={placetype}"
        
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(data)
            if 'features' in data and len(data['features']) > 0:
                feature = data['features'][0]  # Assuming the first feature is the desired one
                if 'geometry' in feature and 'coordinates' in feature['geometry']:
                    coordinates = feature['geometry']['coordinates']
                    longitude, latitude = coordinates[0], coordinates[1]
                    return {'longitude': longitude, 'latitude': latitude}
                else:
                    logger.error(f"No coordinates found for location: {location}")
            else:
                logger.error(f"Unexpected data format or empty response for location: {location}")
        else:
            logger.error(f"API call failed with status code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"API call exception for location {location}: {str(e)}")
    return None

# List of locations to test
locations = ["New York", "Paris", "Tokyo", "Sydney", "Cairo"]

# Test geocoding each location with language and placetype parameters
for location in locations:
    coordinates = call_pelias_api(location, lang='eng', placetype='locality')
    if coordinates:
        print(f"Location: {location}, Coordinates: {coordinates}")
    else:
        print(f"Location: {location}, Coordinates: Not found")
