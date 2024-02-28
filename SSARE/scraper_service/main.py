from fastapi import FastAPI, HTTPException, Query
import requests
from pydantic import BaseModel
from typing import List
import importlib
import json
from fastapi import Body
from celery_worker import scrape_data_task
from core.utils import load_config
from redis.asyncio import Redis
from contextlib import asynccontextmanager
import logging
from core.models import ArticleBase

""""
This Service runs on port 8081 and is responsible for scraping articles.

"""



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()


class Flag(BaseModel):
    flag: str
    




async def setup_redis_connection():
    # Setup Redis connection
    return await Redis(host='redis', port=6379, db=1, decode_responses=True)
async def close_redis_connection(redis_conn):

    # Close Redis connection
    await redis_conn.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Before app startup
    app.state.redis = await setup_redis_connection()
    yield
    # After app shutdown
    await close_redis_connection(app.state.redis)

app = FastAPI(lifespan=lifespan)


def get_scraper_config():
    """
    This function loads the scraper configuration from the JSON file.
    """
    with open("scrapers/scrapers_config.json") as f:
        return json.load(f)

@app.post("/create_scrape_jobs")
async def create_scrape_jobs():
    """
    This function is triggered by an API call from the orchestration container.
    It reads from Redis Queue 0 - channel "scrape_sources" and creates a scraping job for each flag.
    It passes a flag as a string argument to the scrape_single_source function.
    It validates the flags against the scraper configuration.
    The scrape job itself is created by triggering the scrape_data_task function in celery_worker.py.
    -> inside of celery_worker.py:
        The scrape_data_task function reads from the redis queue and create scraping jobs for each flag
        by triggering the scrape_single_source function.
        When the scrape_single_source function is complete, 
        it will push the data to Redis Queue 1 - channel "raw_articles_queue".

    """
    redis_conn_flags = await Redis(host='redis', port=6379, db=0)  # For flags
    logger.info("Creating scrape jobs")
    flags = await redis_conn_flags.lrange('scrape_sources', 0, -1)
    flags = [flag.decode('utf-8') for flag in flags]

    config_json = get_scraper_config()
    if not all(flag in config_json["scrapers"].keys() for flag in flags):
        raise HTTPException(status_code=400, detail="Invalid flags provided.")
    logger.info("Scrape jobs created")
    result = scrape_data_task.delay()
    logger.info(f"Scrape data task created with ID: {result.id}")
    return {"message": "Scraping triggered successfully."}
        

@app.get("/healthz")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}, 200


