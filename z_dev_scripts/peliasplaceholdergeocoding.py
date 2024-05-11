import requests
import logging
import pyPelias

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def call_pelias_api(location, lang=None, placetype=None):
    try:
        # Construct the API URL with optional language and placetype parameters
        url = f"http://136.243.80.175:3000/parser/search?text={location}"
        if lang:
            url += f"&lang={lang}"

        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            item_0 = data[0]
            geometry = item_0['geom']
            lat = geometry['lat']
            lon = geometry['lon']
            return lat, lon
        else:
            logger.error(f"API call failed with status code: {response.status_code}")
    except requests.RequestException as e:
        logger.error(f"API call exception for location {location}: {str(e)}")
    return None

# List of locations to test
locations = ["New York", "Paris", "Tokyo", "Sydney", "Cairo", "London", "Berlin", "Moscow", "Beijing", "Mumbai", "Bangkok", "Istanbul", "Dubai", "Rome", "Seoul", "Mexico City", "Lima", "Buenos Aires", "São Paulo", "Toronto", "Vancouver", "Montreal", "Los Angeles", "San Francisco", "Chicago", "Houston", "Miami", "Washington D.C.", "Atlanta", "Boston", "Barcelona", "Madrid", "Lisbon", "Vienna", "Budapest", "Prague", "Warsaw", "Amsterdam", "Brussels", "Stockholm", "Copenhagen", "Oslo", "Helsinki", "Zurich", "Geneva", "Melbourne", "Perth", "Auckland", "Johannesburg", "Cape Town", "Brandenburger Tor"]

# Test geocoding each location with language and placetype parameters
for location in locations:
    coordinates = call_pelias_api(location, lang='eng')
    if coordinates:
        print(f"Location: {location}, Coordinates: {coordinates}")
    else:
        # print(f"Location: {location}, Coordinates: Not found")
        break
