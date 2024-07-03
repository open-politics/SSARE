from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Tuple
from flair.data import Sentence
from flair.models import SequenceTagger
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, String, Integer, update, cast
from sqlalchemy.dialects.postgresql import JSONB
from redis.asyncio import Redis
from core.utils import load_config
import json
import logging

app = FastAPI()
config = load_config()['postgresql']

# Load the NER model
ner_tagger = SequenceTagger.load("flair/ner-english-ontonotes-large")

# SQLAlchemy setup
Base = declarative_base()

class Article(Base):
    __tablename__ = "articles"
    url = Column(String, primary_key=True)
    entities = Column(JSONB)
    entities_extracted = Column(Integer, default=0)

DATABASE_URL = (
    f"postgresql+asyncpg://{config['postgres_user']}:{config['postgres_password']}@"
    f"{config['postgres_host']}/{config['postgres_db']}"
)
engine = create_async_engine(DATABASE_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.post("/extract_entities")
async def extract_entities(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=6379, db=2)
        article_data = await redis_conn.rpop('articles_without_entities_queue')

        if article_data:
            article = json.loads(article_data)
            url = article['url']
            headline = article['headline']
            paragraphs = article['paragraphs']
            text = headline + paragraphs
            entities = await predict_ner_tags_async(text)

            # Log the type and content of entities
            logger.info(f"Type of entities: {type(entities)}")
            logger.info(f"Content of entities: {entities}")

            # Ensure entities_json is an array of JSON objects
            entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
            entities_json = json.dumps(entities_data)
            logger.info(entities_json)

            async with session.begin():
                query = update(Article).where(Article.url == article['url']).values(entities=entities_json, entities_extracted=1)
                await session.execute(query)

            return {"message": "Entities extracted and article updated successfully."}
        else:
            return {"message": "No articles in the queue."}

    except Exception as e:
        logger.error(f"Error extracting entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def predict_ner_tags_async(text: str) -> List[Tuple[str, str]]:
    """
    Asynchronously predict NER tags for given text using Flair.
    """
    return await asyncio.to_thread(sync_predict_ner_tags, text)

def sync_predict_ner_tags(text: str) -> List[Tuple[str, str]]:
    """
    Synchronously predict NER tags using the Flair model.
    This function will be run in a separate thread to not block the asyncio event loop.
    """
    sentence = Sentence(text)
    ner_tagger.predict(sentence)
    return [(entity.text, entity.tag) for entity in sentence.get_spans('ner')]

# Example endpoint to test the setup (not part of the main requirement)
@app.get("/test")
def test_endpoint():
    return {"message": "Test endpoint working!"}

@app.get("/fetch_entities")
async def fetch_entities(text: str):
    try:
        entities = await predict_ner_tags_async(text)
        entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
        return {"entities": entities_data}
    except Exception as e:
        logger.error(f"Error fetching entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))
