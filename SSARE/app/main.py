import httpx
import os
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi import Request
from fastapi.background import BackgroundTasks
from fastapi import APIRouter
from fastapi.templating import Jinja2Templates
from core.utils import load_config
from redis.asyncio import Redis


### Configuration & Mapping
config = load_config()["postgresql"]
templates = Jinja2Templates(directory="templates")


app = FastAPI()
router = APIRouter()
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
    background_tasks.add_task(execute_scraping_sequence)
    return {"message": "Scraping sequence initiated"}

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

async def execute_scraping_sequence():
    global status_message
    async with httpx.AsyncClient() as client:
        # Step 1: Produce flags
        status_message = "Producing flags..."
        flags_result = await client.get(f"{service_urls['postgres_service']}/flags")
        if flags_result.status_code != 200:
            status_message = "Failed to produce flags."
            return

        # Wait and simulate processing time
        await asyncio.sleep(10)  # Adjust based on your needs

        # Step 2: Trigger scraping
        status_message = "Creating scrape jobs..."
        scrape_result = await client.post(f"{service_urls['scraper_service']}/create_scrape_jobs")
        if scrape_result.status_code != 200:
            status_message = "Failed to create scrape jobs."
            return

        # Wait for scraping to be completed
        await asyncio.sleep(20)  # Adjust based on your needs

        status_message = "Waiting for scraping to complete..."
        await asyncio.sleep(20)  # Adjust based on actual scraping time

        # Step 3: Store raw articles
        status_message = "Storing raw articles..."
        store_raw_result = await client.post(f"{service_urls['postgres_service']}/store_raw_articles")
        if store_raw_result.status_code != 200:
            status_message = "Failed to store raw articles."
            return

        # Wait for storage process
        await asyncio.sleep(10)  # Adjust based on your needs

        # Step 4: Deduplicate articles
        status_message = "Deduplicating articles..."
        deduplicate_result = await client.post(f"{service_urls['postgres_service']}/deduplicate_articles")
        if deduplicate_result.status_code != 200:
            status_message = "Failed to deduplicate articles."
            return

        # Wait for deduplication process
        await asyncio.sleep(10)  # Adjust based on your needs

        # Step 5: Create embedding jobs
        status_message = "Creating embedding jobs..."
        embedding_jobs_result = await client.post(f"{service_urls['postgres_service']}/create_embedding_jobs")
        if embedding_jobs_result.status_code != 200:
            status_message = "Failed to create embedding jobs."
            return

        # Wait for embedding job creation
        await asyncio.sleep(10)  # Adjust based on your needs

        # Step 6: Generate embeddings
        status_message = "Generating embeddings..."
        generate_embeddings_result = await client.post(f"{service_urls['nlp_service']}/generate_embeddings", timeout=400)
        if generate_embeddings_result.status_code != 200:
            status_message = "Failed to generate embeddings."
            return

        # Wait for the embedding process to complete
        await asyncio.sleep(60)  # Adjust based on your needs

        # Step 7: Store articles with embeddings
        status_message = "Storing articles with embeddings..."
        store_embeddings_result = await client.post(f"{service_urls['postgres_service']}/store_articles_with_embeddings")
        if store_embeddings_result.status_code != 200:
            status_message = "Failed to store articles with embeddings."
            return

        # Wait for storage process
        await asyncio.sleep(10)  # Adjust based on your needs

        # Step 8: Trigger pushing articles to Qdrant's queue
        status_message = "Pushing articles to Qdrant queue..."
        push_to_queue_result = await client.post(f"{service_urls['postgres_service']}/trigger_qdrant_queue_push")
        if push_to_queue_result.status_code != 200:
            status_message = "Failed to push articles to Qdrant queue."
            return

        # Brief wait, assuming the queue push is relatively quick
        await asyncio.sleep(2)

        # Final step: Assume we are now storing the embeddings
        status_message = "Storing embeddings in Qdrant..."
        store_result = await client.post(f"{service_urls['qdrant_service']}/store_embeddings")
        if store_result.status_code != 200:
            status_message = "Failed to store embeddings in Qdrant."
            return

        status_message = "Process completed successfully."



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
        queue_length = await redis_conn.llen(queue_key)  # Replace 'queue_key' with your specific key for each channel
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(e)}")

@app.get("/check_channels")
async def check_channels():
    channel_lengths = {}
    for channel, db_info in redis_channel_mappings.items():
        queue_length = await get_redis_queue_length(db_info['db'], db_info['key'])
        channel_lengths[channel] = queue_length
    return channel_lengths

@app.get("/healthcheck")
def print_health():
    return {"message": "OK"}, 200


