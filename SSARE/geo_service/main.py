from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import update
import json
from redis.asyncio import Redis
from geopy.geocoders import Nominatim

# Placeholder imports
from core.utils import load_config  # Make sure this is correctly imported or defined
# from your_project.models import Article  # This should be your SQLAlchemy model import

app = FastAPI()

# Pydantic models
class ArticleEntity(BaseModel):
    text: str
    entity_type: str

class ArticleData(BaseModel):
    url: str
    headline: str
    entities: List[ArticleEntity]

class GeoFeature(BaseModel):
    type: str = "Feature"
    properties: Dict[str, Any]
    geometry: Dict[str, Any]

class GeoJSON(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoFeature]

# Database setup
config = load_config()['postgresql']
DATABASE_URL = (
    f"postgresql+asyncpg://{config['postgres_user']}:{config['postgres_password']}@"
    f"{config['postgres_host']}/{config['postgres_db']}"
)
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session

# Geocoding endpoint
@app.post("/geocode_articles")
async def geocode_articles(session: AsyncSession = Depends(get_session)):
    geolocator = Nominatim(user_agent="geoapiExercises")
    geojson = GeoJSON(features=[])
    redis_conn = await Redis(host='redis', port=6379, db=3)

    article_data_json = await redis_conn.rpop('articles_without_geocoding_queue')
    if article_data_json:
        article_data = json.loads(article_data_json)
        location_articles = {}
        for article in article_data:
            for entity in article['entities']:
                if entity['entity_type'] == "GPE":
                    if entity['text'] not in location_articles:
                        location_articles[entity['text']] = []
                    location_articles[entity['text']].append({
                        'headline': article['headline'],
                        'url': article['url']
                    })

        for location, articles in location_articles.items():
            try:
                location_geo = geolocator.geocode(location)
                if location_geo:
                    feature = GeoFeature(
                        properties={"location": location, "articles": articles},
                        geometry={"type": "Point", "coordinates": [location_geo.longitude, location_geo.latitude]}
                    )
                    geojson.features.append(feature)
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        urls = [article['url'] for article in article_data]
        async with session.begin():
            query = update(Article).where(Article.url.in_(urls)).values(geocoding_created=1)
            await session.execute(query)
        return geojson
    else:
        return {"message": "No articles available for geocoding."}

# Test endpoint
@app.get("/test")
def test_endpoint():
    return {"message": "Test endpoint working!"}

