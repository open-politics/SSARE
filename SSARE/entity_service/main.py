import json
import logging
from typing import List, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends
from flair.data import Sentence
from flair.models import SequenceTagger
from redis import Redis
from sqlmodel import select, SQLModel, Session
from core.models import Article
from core.db import engine, get_session
from core.service_mapping import ServiceConfig
from prefect import task, flow

app = FastAPI()
config = ServiceConfig()

# Load the NER model
ner_tagger = SequenceTagger.load("flair/ner-english-ontonotes-large")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)

@task
def retrieve_article_from_redis(redis_conn) -> dict:
    article_data = redis_conn.rpop('articles_without_entities_queue')
    if article_data:
        return json.loads(article_data)
    return None

@task
def predict_ner_tags(text: str) -> List[Tuple[str, str]]:
    sentence = Sentence(text)
    ner_tagger.predict(sentence)
    return [(entity.text, entity.tag) for entity in sentence.get_spans('ner')]

@task
def process_article(article: dict) -> Tuple[dict, List[Tuple[str, str]]]:
    text = article['headline'] + " " + article['paragraphs']
    entities = predict_ner_tags(text)
    return (article, entities)

@task
def update_article_with_entities(article_data: dict, entities: List[Tuple[str, str]], session: Session):
    try:
        article = session.exec(select(Article).where(Article.url == article_data['url'])).first()
        if article:
            entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
            article.entities = json.dumps(entities_data)
            article.entities_extracted = 1
            session.add(article)
            session.commit()
            logger.info(f"Entities extracted and updated for article: {article_data['url']}")
        else:
            logger.warning(f"Article not found: {article_data['url']}")
    except Exception as e:
        logger.error(f"Error updating article {article_data['url']}: {str(e)}")
        session.rollback()

@flow
def extract_entities_endpoint():
    logger.info("Starting entity extraction process")
    redis_conn = Redis(host='redis', port=6379, db=2, decode_responses=True)
    
    try:
        article = retrieve_article_from_redis(redis_conn)
        if article:
            article_data, entities = process_article(article)
            with Session(engine) as session:
                update_article_with_entities(article_data, entities, session)
            logger.info(f"Entities extracted and updated for article: {article_data['url']}")
        else:
            logger.info("No articles found in the queue.")
    finally:
        redis_conn.close()

    return {"message": "Entity extraction completed"}

@app.post("/extract_entities")
def generate_entities():
    logger.info("Generating entities")
    return extract_entities_endpoint()

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