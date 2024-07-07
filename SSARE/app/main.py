import httpx
import os
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from core.utils import load_config
from redis.asyncio import Redis
from flows.orchestration import scraping_flow
from prefect import get_client
from fastapi.staticfiles import StaticFiles 
from fastapi.responses import JSONResponse
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



# Configuration & Mapping
config = load_config()["postgresql"]
templates = Jinja2Templates(directory="templates")

# El App
app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")  # new line

router = APIRouter()
app.include_router(router)
status_message = "Ready to start scraping."

redis_channel_mappings = {
    "flags": {"db": 0, "key": "scrape_sources"},
    "raw_articles": {"db": 1, "key": "raw_articles"},
    "processed_articles": {"db": 2, "key": "processed_articles"},
    "articles_without_embedding_queue": {"db": 5, "key": "articles_without_embedding_queue"},
    "articles_with_embeddings": {"db": 6, "key": "articles_with_embeddings"},
}

runtime_url = "http://main_core_app:8089"

service_urls = {
    "main_core_app": runtime_url,
    "postgres_service": "http://postgres_service:5434",
    "nlp_service": "http://nlp_service:0420",
    "qdrant_service": "http://qdrant_service:6969",
    "qdrant_storage": "http://qdrant_storage:6333",
    "scraper_service": "http://scraper_service:8081",
}

### Healthcheck & Monitoring

@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}, 200

## Monitoring
#- Dashboard
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, search_query: str = "culture and arts"):
    qdrant_service_url = service_urls["qdrant_service"] + '/search'
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            qdrant_service_url,
            params={
                "query": search_query,
                "top": 25,
            }
        )

    if response.is_success:
        articles = response.json()['data']
        articles = [{
            'score': article['score'],
            'headline': article['headline'],
            'paragraphs': article['paragraphs'],
            'url': article['url']
        } for article in articles]
        logger.info("Response for search was successful")
    else:
        articles = []     
        logger.info("Response for search was not successful")

    if "HX-Request" in request.headers:
        return templates.TemplateResponse("partials/articles_list.html", {"request": request, "articles": articles})
    else:
        return templates.TemplateResponse("index.html", {"request": request, "search_query": search_query})

import asyncio

@app.post("/trigger_scraping_sequence")
async def trigger_scraping_flow():
    try:
        asyncio.create_task(scraping_flow())
        return {"message": "Scraping flow triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger scraping flow: {str(e)}")

@app.get("/check_services")
async def check_services():
    service_statuses = {}
    for service, url in service_urls.items():
        try:
            response = await httpx.get(url + "/health", timeout=10.0)
            # if not try healthz
            
            service_statuses[service] = response.status_code
        except httpx.RequestError as e:
            service_statuses[service] = str(e)
    return service_statuses

import subprocess

@app.post("/trigger_scraping")
async def trigger_scraping():
    try:
        subprocess.run(["python", "flows/orchestration.py"], check=True)
        return {"message": "Scraping flow triggered"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger scraping flow: {str(e)}")

@app.post("/store_embeddings_in_qdrant")
async def store_embeddings_in_qdrant():
    response = await httpx.post(service_urls["qdrant_service"] + "/store_embeddings")
    if response.status_code == 200:
        return {"message": "Embeddings storage in Qdrant triggered successfully."}
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to trigger embeddings storage in Qdrant.")

async def get_redis_queue_length(redis_db: int, queue_key: str):
    try:
        redis_conn = Redis(host='redis', port=6379, db=redis_db)
        queue_length = await redis_conn.llen(queue_key)
        return queue_length  # Add this line to return the queue length
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(e)}")
    
@app.get("/check_channels")
async def check_channels():
    channel_lengths = {}
    for channel, db_info in redis_channel_mappings.items():
        try:
            queue_length = await get_redis_queue_length(db_info['db'], db_info['key'])
            channel_lengths[channel] = queue_length
        except HTTPException as e:
            channel_lengths[channel] = f"Error: {str(e)}"  # Set a default value in case of an error
    return channel_lengths

@app.get("/service_health", response_class=JSONResponse)
async def service_health():
    health_status = {}
    async with httpx.AsyncClient() as client:
        for service, url in service_urls.items():
            try:
                response = await client.get(f"{url}/healthz", timeout=5.0)
                if response.status_code == 200:
                    health_status[service] = "green"
                else:
                    health_status[service] = "red"
            except httpx.RequestError:
                health_status[service] = "red"
    return health_status

@app.get("/healthcheck")
def print_health():
    return {"message": "OK"}, 200
