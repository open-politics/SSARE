import json
import logging
from typing import List, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from flair.data import Sentence
from flair.models import SequenceTagger
from redis import Redis
from core.service_mapping import ServiceConfig
from core.models import Article, Entity
from prefect import task, flow
import uuid

app = FastAPI()
config = ServiceConfig()

# Load the NER model
ner_tagger = SequenceTagger.load("flair/ner-english-ontonotes-large")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

@task
def retrieve_articles_from_redis(redis_conn, batch_size=50) -> List[Article]:
    batch = redis_conn.lrange('articles_without_entities_queue', 0, batch_size - 1)
    redis_conn.ltrim('articles_without_entities_queue', batch_size, -1)
    return [Article(**json.loads(article)) for article in batch]

@task
def predict_ner_tags(text: str) -> List[Tuple[str, str]]:
    sentence = Sentence(text)
    ner_tagger.predict(sentence)
    return [(entity.text, entity.tag) for entity in sentence.get_spans('ner')]

@task
def process_article(article: Article) -> Tuple[Article, List[Tuple[str, str]]]:
    text = ""
    if article.headline:
        text += article.headline + " "
    if article.paragraphs:
        text += article.paragraphs
    entities = predict_ner_tags(text.strip())
    return (article, entities)

@task
def push_articles_with_entities(redis_conn, articles_with_entities: List[Tuple[Article, List[Tuple[str, str]]]]):
    try:
        for article, entities in articles_with_entities:
            entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
            article_dict = article.dict()
            article_dict['entities'] = entities_data
            
            # Convert UUID fields to strings
            for key, value in article_dict.items():
                if isinstance(value, uuid.UUID):
                    article_dict[key] = str(value)
            
            redis_conn.lpush('articles_with_entities_queue', json.dumps(article_dict))
            logger.info(f"Article with entities pushed to queue: {article.url}")
    except Exception as e:
        logger.error(f"Error pushing articles with entities to queue: {str(e)}")

@flow
def extract_entities_flow(batch_size: int):
    logger.info("Starting entity extraction process")
    redis_conn = Redis(host='redis', port=6379, db=2, decode_responses=True)
    
    try:
        articles = retrieve_articles_from_redis(redis_conn, batch_size)
        if articles:
            articles_with_entities = [process_article(article) for article in articles]
            push_articles_with_entities(redis_conn, articles_with_entities)
            logger.info(f"Entities extracted for {len(articles)} articles.")
        else:
            logger.info("No articles found in the queue.")
    finally:
        redis_conn.close()

    return {"message": "Entity extraction completed"}

@app.post("/extract_entities")
def generate_entities(batch_size: int = 50):
    logger.info("Generating entities")
    return extract_entities_flow(batch_size)

@app.get("/healthz")
def healthz():
    return {"message": "ok"}

@app.get("/fetch_entities")
def fetch_entities(text: str):
    try:
        entities = predict_ner_tags(text)
        entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
        return {"entities": entities_data}
    except Exception as e:
        logger.error(f"Error fetching entities: {e}")
        raise HTTPException(status_code=500, detail=str(e))