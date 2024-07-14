from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import update
import json
from redis.asyncio import Redis
import logging
from collections import Counter
import requests

# Import service_urls from core.service_mapping
from core.service_mapping import ServiceConfig

config=ServiceConfig()

# from your_project.models import Article  # This should be your SQLAlchemy model import
from pydantic import BaseModel

from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, ARRAY, Integer, Float
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class Article(Base):
    __tablename__ = "articles"
    url = Column(String, primary_key=True)  # Url & Unique Identifier
    headline = Column(String)  # Headline
    paragraphs = Column(String)  # Text
    source = Column(String)  # 'cnn'
    embeddings = Column(ARRAY(Float))  # [3223, 2342, ..]
    entities = Column(JSONB)  # JSONB for storing entities
    geocodes = Column(ARRAY(JSONB))  # JSON objects for geocodes
    embeddings_created = Column(Integer, default=0)  # Flag
    stored_in_qdrant = Column(Integer, default=0)  # Flag
    entities_extracted = Column(Integer, default=0)  # Flag
    geocoding_created = Column(Integer, default=0)  # Flag

app = FastAPI()

# Pydantic models
class ArticleEntity(BaseModel):
    text: str
    entity_type: str

class ArticleData(BaseModel):
    url: str
    headline: str
    entities: str  # Changed to str to accommodate JSON string
    paragraphs: str  # New field

class GeoFeature(BaseModel):
    type: str = "Feature"
    properties: Dict[str, Any]
    geometry: Dict[str, Any]

class GeoJSON(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoFeature]

# Database setup
DATABASE_URL = (
    f"postgresql+asyncpg://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
    f"@postgres_service:{config.ARTICLES_DB_PORT}/{config.ARTICLES_DB_NAME}"
)

engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Geocoding endpoint
@app.post("/geocode_articles")
async def geocode_articles(session: AsyncSession = Depends(get_session)):
    redis_conn = await Redis(host='redis', port=6379, db=3)
    article_data_json = await redis_conn.rpop('articles_without_geocoding_queue')

    if article_data_json:
        article_data_json = article_data_json.decode('utf-8')
        article_data = json.loads(article_data_json)
        entities = json.loads(article_data['entities'])

        if 'entities' in article_data and isinstance(entities, list):
            location_entities = [entity for entity in entities if entity['tag'] == "GPE"]
            location_counts = Counter(entity['text'] for entity in location_entities)
            total_locations = len(location_entities)
            location_weights = {location: count / total_locations for location, count in location_counts.items()}

            geocoded_locations = []
            for location, weight in location_weights.items():
                coordinates = call_pelias_api(location, lang='en')
                if coordinates:
                    geocoded_locations.append({
                        "location": location,
                        "weight": weight,
                        "coordinates": coordinates
                    })
                    logger.info(f"Geocoded location {location} with coordinates {coordinates}.")
                else:
                    logger.error(f"Error geocoding location {location}: No coordinates found.")

            async with session.begin():
                update_query = update(Article).where(Article.url == article_data['url']).values(geocodes=geocoded_locations)
                await session.execute(update_query)
                await session.commit()

            return {"geocoded_locations": geocoded_locations}
        else:
            return {"message": "No valid entities available for geocoding."}
    else:
        return {"message": "No articles available for geocoding."}

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
        pelias_url = config.PELIAS_PLACEHOLDER_URL
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

# Test endpoint
@app.get("/test")
def test_endpoint():
    return {"message": "Test endpoint working!"}
