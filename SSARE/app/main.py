import httpx
import os
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, APIRouter
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from core.utils import load_config
from redis.asyncio import Redis
from .orchestration import scraping_flow

### Configuration & Mapping
config = load_config()["postgresql"]
templates = Jinja2Templates(directory="templates")

app = FastAPI()
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

runtime_url = "http://main_core_app:8080"

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
    # Use the internal service URL for qdrant_service you defined in service_urls
    qdrant_service_url = service_urls["qdrant_service"] + '/search'
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            qdrant_service_url,
            params={
                "query": search_query,
                "top": 25,
            }
        )
    
    # Ensure the response is successful before proceeding to parse the JSON
    if response.is_success:
        articles = response.json()
    else:
        articles = []  # Or handle the error as you see fit
    
    # Check if the request is from HTMX
    if "HX-Request" in request.headers:
        # If it is an HTMX request, return only the articles list part
        return templates.TemplateResponse("partials/articles_list.html", {"request": request, "articles": articles})
    else:
        # For a normal request, return the entire page
        return templates.TemplateResponse("index.html", {"request": request, "articles": articles, "search_query": search_query})

@router.get("/scraping_status")
async def get_scraping_status():
    return {"status": status_message}

@app.post("/trigger_scraping_sequence")
async def trigger_scraping_sequence(background_tasks: BackgroundTasks):
    global status_message
    status_message = "Scraping initiated..."
    background_tasks.add_task(scraping_flow)
    return HTMLResponse(content="<div>Scraping sequence initiated</div>")

@app.get("/check_services")
async def check_services():
    service_statuses = {}
    for service, url in service_urls.items():
        try:
            response = await httpx.get(url + "/health", timeout=10.0)
            service_statuses[service] = response.status_code
        except httpx.RequestError as e:
            service_statuses[service] = str(e)
    return service_statuses

@app.post("/trigger_scraping")
async def trigger_scraping():
    response = await httpx.post(service_urls["scraper_service"] + "/create_scrape_jobs")
    if response.status_code == 200:
        return {"message": "Scraping jobs triggered successfully."}
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to trigger scraping jobs.")

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


@app.get("/healthcheck")
def print_health():
    return {"message": "OK"}, 200
