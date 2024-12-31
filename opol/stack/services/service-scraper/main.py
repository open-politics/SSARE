from fastapi import FastAPI, HTTPException, Query
from redis.asyncio import Redis
from contextlib import asynccontextmanager
import logging
from prefect import task, flow
from core.models import Content
from core.db import engine, get_session
import json
import asyncio
from newspaper import Article
from core.utils import logger
from core.service_mapping import get_redis_url
from prefect.deployments import run_deployment
from fastapi import APIRouter

from polls.routes import router as polls_router
from legislation.routes import router as legislation_router
from economic.routes import router as economic_router

@task
async def setup_redis_connection():
    return Redis.from_url(get_redis_url(), db=1, decode_responses=True)

@task
async def close_redis_connection(redis_conn):
    try:
        await redis_conn.aclose()
    except RuntimeError as e:
        logger.warning(f"Error closing Redis connection: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_conn = Redis.from_url(get_redis_url(), db=1, decode_responses=True)
    app.state.redis = redis_conn
    yield
    await redis_conn.aclose()

app = FastAPI(lifespan=lifespan)

app.include_router(polls_router, tags=["polls"])
app.include_router(legislation_router, tags=["legislation"])
app.include_router(economic_router, tags=["economic"])
@task
async def get_scraper_config():
    with open("scrapers/scrapers_config.json") as f:
        return json.load(f)

@task
async def get_flags():
    redis_conn_flags = Redis.from_url(get_redis_url(), db=0, decode_responses=True)
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

        await run_deployment(
            name="Scrape Sources Flow/scrape-sources-deployment",
            parameters={"flags": flags}
        )

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

@task
@app.get("/scrape_article")
async def scrape_article(url: str = Query(..., description="The URL of the article to scrape")):
    try:
        logger.error(f"Starting to scrape article from URL: {url}")
        
        article = Article(url)
        logger.error("Article object created, starting download")
        
        await asyncio.to_thread(article.download)  # Run download in a separate thread
        logger.error("Article downloaded successfully, starting parsing")
        
        await asyncio.to_thread(article.parse)  # Run parse in a separate thread
        logger.info("Article parsed successfully")

        # Extract top image and publication date
        text = article.text if article.text else None
        url = article.url if article.url else None
        top_image = article.top_image if "placeholder" not in article.top_image else None
        summary = article.meta_description if "dw.com" in url or "cnn.com" in url else article.summary if article.summary else None
        meta_summary = None if "dw.com" in url or "cnn.com" in url else article.meta_description if article.meta_description else None
        logger.info(f"Extracted top image: {top_image}")
        
        publication_date = article.publish_date.isoformat() if article.publish_date else None
        logger.info(f"Extracted publication date: {publication_date}")

        response = {
            "url": url,
            "text_content": text,
            "top_image": top_image,
            "publication_date": publication_date,
            "summary": summary,
            "meta_summary": meta_summary
        }
        logger.info(f"Successfully scraped article with response: {response}")
        return response
        
    except Exception as e:
        logger.error(f"Error scraping article {url}: {e}")
        logger.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=f"Error scraping article: {str(e)}")



