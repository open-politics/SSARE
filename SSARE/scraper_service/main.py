import json
import logging
from fastapi import FastAPI, HTTPException
from redis.asyncio import Redis
from contextlib import asynccontextmanager
from prefect import task, flow
from core.models import Content
from core.db import engine, get_session
from core.utils import logger
import asyncio
from script_scraper import scrape_sources_flow

@task
async def setup_redis_connection():
    return Redis(host='redis', port=6379, db=1, decode_responses=True)

@task
async def close_redis_connection(redis_conn):
    try:
        await redis_conn.aclose()
    except RuntimeError as e:
        logger.warning(f"Error closing Redis connection: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_conn = await setup_redis_connection()
    app.state.redis = redis_conn
    yield
    await close_redis_connection(redis_conn)

app = FastAPI(lifespan=lifespan)

@task
async def get_scraper_config():
    with open("scrapers/scrapers_config.json") as f:
        return json.load(f)

@task
async def get_flags():
    redis_conn_flags = Redis(host='redis', port=6379, db=0, decode_responses=True)
    flags = await redis_conn_flags.lrange('scrape_sources', 0, -1)
    await redis_conn_flags.aclose()
    return flags

@task
async def wait_for_scraping_completion(redis_conn):
    while await redis_conn.get('scrapers_running') == '1':
        await asyncio.sleep(0.5)

@flow
async def scrape_data():
    redis_conn = await setup_redis_connection()
    try:
        flags = await get_flags()
        logger.info(f"Creating scrape jobs for {flags}")

        await scrape_sources_flow(flags)

        await wait_for_scraping_completion(redis_conn)
    except Exception as e:
        logger.error(f"Error in scrape_data flow: {str(e)}")
    finally:
        await close_redis_connection(redis_conn)
    logger.info(f"Scrape data task completed.")
    return {"status": "ok"}

@app.post("/create_scrape_jobs")
async def create_scrape_jobs():
    return await scrape_data()

@app.get("/healthz")
def healthz_check():
    return {"status": "ok"}
