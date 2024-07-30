import httpx
import os
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis
from flows.orchestration import scraping_flow
from prefect import get_client
from fastapi.staticfiles import StaticFiles 
from fastapi.responses import JSONResponse
from fastapi import Query
import logging
from core.service_mapping import ServiceConfig
import asyncio
import subprocess
from flows.orchestration import (
    deduplicate_articles, create_embedding_jobs, generate_embeddings,
    store_articles_with_embeddings, create_entity_extraction_jobs,
    extract_entities, store_articles_with_entities,
    create_geocoding_jobs, geocode_articles,
    produce_flags, create_scrape_jobs, store_raw_articles
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration & Mapping
templates = Jinja2Templates(directory="templates")

# El App
app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

router = APIRouter()
app.include_router(router)
status_message = "Ready to start scraping."

config = ServiceConfig()

### Healthcheck & Monitoring

@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}

## Monitoring
#- Dashboard
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, query: str = "culture and arts"):
    rag_service_url = f"{config.service_urls['rag_service']}/search"
    async with httpx.AsyncClient() as client:
        response = await client.post(
            rag_service_url,
            params={
                "query": query,
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
        return templates.TemplateResponse("index.html", {"request": request, "search_query": query})

@app.post("/trigger_scraping_sequence")
async def trigger_scraping_flow():
    logger.info("Triggering scraping flow")
    try:
        asyncio.create_task(scraping_flow())
        return {"message": "Scraping flow triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger scraping flow: {str(e)}")

@app.get("/check_services")
async def check_services():
    service_statuses = {}
    for service, url in config.SERVICE_URLS.items():
        try:
            response = await httpx.get(f"{url}/healthz", timeout=10.0)
            service_statuses[service] = response.status_code
        except httpx.RequestError as e:
            service_statuses[service] = str(e)
    return service_statuses

@app.post("/trigger_scraping")
async def trigger_scraping():
    try:
        logger.info("Triggering scraping flow")
        subprocess.run(["python", "flows/orchestration.py"], check=True)
        return {"message": "Scraping flow triggered"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger scraping flow: {str(e)}")

@app.post("/store_embeddings_in_qdrant")
async def store_embeddings_in_qdrant():
    response = await httpx.post(f"{config.SERVICE_URLS['qdrant_service']}/store_embeddings")
    if response.status_code == 200:
        return {"message": "Embeddings storage in Qdrant triggered successfully."}
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to trigger embeddings storage in Qdrant.")

async def get_redis_queue_length(redis_db: int, queue_key: str):
    try:
        redis_conn = Redis(host=os.getenv('REDIS_HOST', 'redis'), port=int(os.getenv('REDIS_PORT', 6379)), db=redis_db)
        queue_length = await redis_conn.llen(queue_key)
        return queue_length
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(e)}")
    
@app.get("/check_channels")
async def check_channels(request: Request):
    channel_info = {}
    redis_conn = Redis(host='redis', port=6379, decode_responses=True)
    
    # Fetch information for all Redis queues defined in ServiceConfig
    for queue_name, queue_info in ServiceConfig.redis_queues.items():
        db = queue_info['db']
        key = queue_info['key']
        redis_conn.select(db)
        
        if key == 'scraping_in_progress':
            value = await redis_conn.get(key)
            channel_info[queue_name] = 'Active' if value == '1' else 'Inactive'
        else:
            channel_info[queue_name] = await redis_conn.llen(key)
    
    await redis_conn.aclose()
    
    logger.info(f"Channel info: {channel_info}")

    # Check if it's an HTMX request
    if request.headers.get("HX-Request") == "true":
        # Return HTML response for HTMX
        return templates.TemplateResponse("partials/channel_info.html", {"request": request, "channel_info": channel_info})
    else:
        # Return JSON response for API requests
        return JSONResponse(content=channel_info)

@app.get("/service_health", response_class=HTMLResponse)
async def service_health(request: Request):
    health_status = {}
    services_to_check = [
        "main_core_app",
        "postgres_service",
        "nlp_service",
        "scraper_service",
        "r2r",
        "rag_service",
        "entity_service",
        "geo_service"
    ]
    async with httpx.AsyncClient() as client:
        for service in services_to_check:
            url = config.service_urls.get(service)
            if url:
                try:
                    response = await client.get(f"{url}/healthz", timeout=5.0)
                    if response.status_code == 200:
                        health_status[service] = "green"
                    else:
                        health_status[service] = "red"
                except httpx.RequestError:
                    health_status[service] = "red"
            else:
                health_status[service] = "gray"
    
    return templates.TemplateResponse("partials/service_health.html", {"request": request, "service_health": health_status})

@app.post("/trigger_step/{step_name}")
async def trigger_step(step_name: str):
    step_functions = {
        "produce_flags": produce_flags,  # Add this function
        "create_scrape_jobs": create_scrape_jobs,  # Add this function
        "store_raw_articles": store_raw_articles,  # Ad
        "deduplicate_articles": deduplicate_articles,
        "create_embedding_jobs": create_embedding_jobs,
        "generate_embeddings": generate_embeddings,
        "store_articles_with_embeddings": store_articles_with_embeddings,
        "create_entity_extraction_jobs": create_entity_extraction_jobs,
        "extract_entities": extract_entities,
        "store_articles_with_entities": store_articles_with_entities,
        "create_geocoding_jobs": create_geocoding_jobs,
        "geocode_articles": geocode_articles,
    }
    
    if step_name not in step_functions:
        raise HTTPException(status_code=400, detail="Invalid step name")
    
    try:
        result = await step_functions[step_name]()
        return {"message": f"Step '{step_name}' completed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute step '{step_name}': {str(e)}")
    
@app.get("/articles", response_class=HTMLResponse)
async def search_articles(
    request: Request,
    search_text: str = Query(None),
    has_embedding: bool = Query(False),
    has_geocoding: bool = Query(False),
    has_entities: bool = Query(False),
    skip: int = 0,
    limit: int = 10
):
    postgres_service_url = f"{config.service_urls['postgres_service']}/articles"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            postgres_service_url,
            params={
                "search_text": search_text,
                "has_embedding": has_embedding,
                "has_geocoding": has_geocoding,
                "has_entities": has_entities,
                "skip": skip,
                "limit": limit
            }
        )

    if response.status_code == 200:
        articles = response.json()
        return templates.TemplateResponse("partials/search_results.html", {"request": request, "articles": articles})
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch articles from PostgreSQL service")