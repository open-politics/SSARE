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

app = FastAPI()

class Article(BaseModel):
    url: str
    headline: str
    paragraphs: List[str]

async def setup_redis_connection():
    # Setup Redis connection
    return await Redis(host='redis', port=6379, db=0, decode_responses=True)
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
    with open("./scrapers/config.json") as f:
        return json.load(f)

@app.post("create_scrape_jobs")
def create_scrape_jobs(flags: List[str] = Body(...)):
    # Get the scraper config
    config_json = get_scraper_config()

    # Get the flags from the request body
    flags = flags

    # Check if the flags are valid
    if not all(flag in config_json["scrapers"].keys() for flag in flags):
        raise HTTPException(status_code=400, detail="Invalid flags provided.")

    # Trigger the scraping task
    scrape_data_task.delay(flags)

    return {"message": "Scraping triggered successfully."}
        

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


