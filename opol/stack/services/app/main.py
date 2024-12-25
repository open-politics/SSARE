# Standard library imports
import os
import asyncio
import subprocess
from enum import Enum

# Third-party imports
import httpx
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, APIRouter, Path, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis
# from prefect import task, flow, deploy
# from prefect.deployments import run_deployment
from pydantic import BaseModel
from fastapi.logger import logger
import logging
from jinja2 import Environment, FileSystemLoader

# Local imports
from core.service_mapping import ServiceConfig
from core.utils import get_redis_url


templates = Jinja2Templates(directory="templates")
config = ServiceConfig()


# FastAPI Setup
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
router = APIRouter()
app.include_router(router)
status_message = "Ready to start scraping."

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.access")
logger.setLevel(logging.WARNING) 

### API Endpoints grouped by functionality

## Health and Monitoring
@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}

@app.get("/service_health", response_class=HTMLResponse)
async def service_health(request: Request):
    health_status = {}
    services_to_check = [
        "app",
        "postgres-service",
        "embedding-service",
        "scraper-service",
        "r2r",
        "rag-service",
        "entity-service",
        "geo-service",
        "ollama",
        "liteLLM",
        "classification-service"
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

@app.get("/check_services")
async def check_services():
    service_statuses = {}
    for service, url in config.service_urls.items():
        try:
            response = await httpx.get(f"{url}/healthz", timeout=10.0)
            service_statuses[service] = response.status_code
        except httpx.RequestError as e:
            service_statuses[service] = str(e)
    return service_statuses

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("opol.html", {"request": request})

## Main Application Routes
@app.get("/dashboardx", response_class=HTMLResponse)
async def read_root(background_tasks: BackgroundTasks, request: Request, query: str = "culture and arts"):
    try:
        postgres_service_url = f"{config.service_urls['postgres-service']}/contents"
        
        # Add the query task to the background
        background_tasks.add_task(fetch_contents, postgres_service_url, query, request)

        use_local_prefect_server = os.getenv("LOCAL_PREFECT", "false").lower() == "true"
        if use_local_prefect_server:
            prefect_dashboard_url = "http://localhost:4200/dashboard"
        else:
            workspace_id = os.getenv("PREFECT_WORKSPACE_ID")
            workspace = os.getenv("PREFECT_WORKSPACE")
            prefect_dashboard_url = f"https://app.prefect.cloud/account/{workspace_id}/workspace/{workspace}/dashboard"

        return templates.TemplateResponse("index.html", {
            "request": request,
            "search_query": query,
            "prefect_dashboard_url": prefect_dashboard_url
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load dashboard: {str(e)}")

async def fetch_contents(postgres_service_url, query, request):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            postgres_service_url,
            params={
                "search_query": query,
                "search_type": "semantic",
                "skip": 0,
                "limit": 10
            }
        )

    if response.status_code == 200:
        contents = response.json()
        contents = [{
            'score': content.get('similarity', 0),
            'headline': content['title'],
            'paragraphs': content['text_content'],
            'url': content['url']
        } for content in contents]
        # You might want to store or process the contents here
    else:
        # Handle the error or log it
        pass

@app.get("/contents", response_class=HTMLResponse)
async def search_contents(
    request: Request,
    search_query: str = Query(None),
    search_type: str = Query("text"),
    skip: int = 0,
    limit: int = 10
):
    postgres_service_url = f"{config.service_urls['postgres-service']}/contents"
    async with httpx.AsyncClient() as client:
        response = await client.get(
            postgres_service_url,
            params={
                "search_query": search_query,
                "search_type": search_type,
                "skip": skip,
                "limit": limit
            }
        )

    if response.status_code == 200:
        contents = response.json()
        return templates.TemplateResponse("partials/search_results.html", {"request": request, "contents": contents})
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to fetch contents from PostgreSQL service")

@app.get("/outward_irrelevant_articles", response_class=HTMLResponse)
async def outward_irrelevant_articles(request: Request):
    """Fetch and display articles marked as outward/irrelevant."""
    try:
        postgres_service_url = f"{config.service_urls['postgres-service']}/outward_irrelevant"
        async with httpx.AsyncClient() as client:
            response = await client.get(postgres_service_url)

        if response.status_code == 200:
            articles = response.json()
            # Display raw JSON data in a simple HTML field
            return templates.TemplateResponse("partials/outward_irrelevant_articles.html", {"request": request, "articles": articles})
        else:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch outward/irrelevant articles")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching outward/irrelevant articles: {str(e)}")

## Pipeline Management
@app.get("/pipeline/{pipeline_name}", response_class=HTMLResponse)
async def get_pipeline(request: Request, pipeline_name: str):
    pipelines = {
        "scraping": {
            "title": "Scraping Pipeline",
            "input": "Flags",
            "output": "Raw Contents",
            "steps": [
                {"name": "produce_flags", "label": "1. Produce Flags"},
                {"name": "create_scrape_jobs", "label": "2. Scrape"},
                {"name": "store_raw_contents", "label": "3. Store Raw Contents"}
            ]
        },
        "embedding": {
            "title": "Embedding Pipeline",
            "input": "Raw Contents",
            "output": "Embedded Contents",
            "steps": [
                {"name": "create_embedding_jobs", "label": "1. Create Jobs"},
                {"name": "generate_embeddings", "label": "2. Generate", "batch": True},
                {"name": "store_contents_with_embeddings", "label": "3. Store"}
            ]
        },
        "entity_extraction": {
            "title": "Entity Extraction Pipeline",
            "input": "Raw Contents",
            "output": "Contents with Entities",
            "steps": [
                {"name": "create_entity_extraction_jobs", "label": "1. Create Jobs"},
                {"name": "extract_entities", "label": "2. Extract", "batch": True},
                {"name": "store_contents_with_entities", "label": "3. Store"}
            ]
        },
        "geocoding": {
            "title": "Geocoding Pipeline",
            "input": "Contents with Entities",
            "output": "Geocoded Contents",
            "steps": [
                {"name": "create_geocoding_jobs", "label": "1. Create Jobs"},
                {"name": "geocode_contents", "label": "2. Geocode", "batch": True},
                {"name": "store_contents_with_geocoding", "label": "3. Store"}
            ]
        },
        "classification": {
            "title": "Classification Pipeline",
            "input": "Processed Contents",
            "output": "Classified Contents",
            "steps": [
                {"name": "create_classification_jobs", "label": "1. Create Jobs"},
                {"name": "classify_contents", "label": "2. Process", "batch": True},
                {"name": "store_contents_with_classification", "label": "3. Store"}
            ]
        }
    }
    
    pipeline = pipelines.get(pipeline_name)
    if not pipeline:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    
    return templates.TemplateResponse("partials/pipeline.html", {
        "request": request,
        "pipeline": pipeline,
        "pipeline_name": pipeline_name
    })

async def setup_redis_connection():
    """Create and return a Redis connection."""
    try:
        redis_conn = Redis.from_url(
            url=str(get_redis_url()),
            decode_responses=True
        )
        return redis_conn
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to connect to Redis")


from flows.orchestration import geocode_contents

@app.post("/trigger_step/{step_name}")
async def trigger_step(step_name: str, batch_size: int = Query(50, ge=1, le=100)):
    try:
        # Add context initialization
        redis_conn = await setup_redis_connection()

        # Only relevant flows
        saving_steps = {
            "store_raw_contents": "save-raw-contents-flow/save-raw-contents",
            "store_contents_with_embeddings": "save-contents-with-embeddings-flow/save-contents-with-embeddings",
            "store_contents_with_entities": "save-contents-with-entities-flow/save-contents-with-entities",
            "store_contents_with_geocoding": "save-geocoded-contents-flow/save-geocoded-contents",
            "store_contents_with_classification": "save-contents-with-classification-flow/save-contents-with-classification"
        }


        # Let all creation steps call the aggregated one
        job_creation_steps = {
            "produce_flags": "produce-flags-flow/produce-flags-deployment",
            "create_scrape_jobs": "scrape-sources-deployment",
            "create_embedding_jobs": "create-embedding-jobs",
            "create_entity_extraction_jobs": "create-entity-extraction-jobs",
            "create_geocoding_jobs": "create-geocoding-jobs",
            "create_classification_jobs": "create-classification-jobs"
        }

        process_steps = {
            "scrape_sources": "Scrape Sources Flow/scrape-sources-deployment",
            "generate_embeddings": "generate-embeddings-flow/generate-embeddings-deployment",
            "extract_entities": "extract-entities-flow/extract-entities-deployment",
            "classify_contents": "classify-contents-deployment",
            "geocode_contents": "geocode-locations-flow/geocode-locations-deployment"
        }

        if step_name in saving_steps:
            deployment_name = saving_steps[step_name]
        elif step_name in job_creation_steps:
            # Always create jobs for all
            deployment_name = "create-jobs-flow/create-jobs"
        elif step_name in process_steps:
            deployment_name = process_steps[step_name]
        
        exec = subprocess.run(["prefect", "deployment", "run", deployment_name], check=True)
    

        await redis_conn.aclose()  # Clean up
        return {"message": f"Step '{step_name}' completed successfully", "deployment_id": exec.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

## Redis Channel Management
@app.get("/check_channels/{flow_name}", response_class=HTMLResponse)
async def check_channels(request: Request, flow_name: str):
    channels = {}
    try:
        redis_url = get_redis_url()
        try:
            redis_conn = Redis.from_url(redis_url, decode_responses=True)
            await redis_conn.ping()
        except Exception as e:
            logger.error(f"Failed to connect to Redis at {redis_url}: {e}")
            raise HTTPException(status_code=500, detail="Error connecting to Redis")
        
        flow_channels = {
            "status": {"Orchestration_in_progress"},
            "scrapers_running": {"scrapers_running"},
            "scraping": ["scrape_sources", "raw_contents_queue"],
            "embedding": ["contents_without_embedding_queue", "contents_with_embeddings"],
            "entity_extraction": ["contents_without_entities_queue", "contents_with_entities_queue"],
            "geocoding": ["contents_without_geocoding_queue", "contents_with_geocoding_queue"],
            "semantics": ["contents_without_tags_queue", "contents_with_tags_queue"],
            "classification": ["contents_without_classification_queue", "contents_with_classification_queue"],
            "failed_geocodes": ["failed_geocodes_queue"]
        }
        
        if flow_name not in flow_channels:
            raise HTTPException(status_code=404, detail=f"Invalid flow name: {flow_name}")
        
        for channel_name in flow_channels[flow_name]:
            queue_info = config.redis_queues.get(channel_name)
            if queue_info:
                try:
                    await redis_conn.select(queue_info['db'])
                    if channel_name in ['Orchestration_in_progress', 'scrapers_running']:
                        value = await redis_conn.get(queue_info['key'])
                        channels[channel_name] = 'Active' if value == '1' else 'Inactive'
                    else:
                        value = await redis_conn.llen(queue_info['key'])
                        channels[channel_name] = int(value)  # Ensure numeric value
                except Exception as e:
                    logger.error(f"Error accessing Redis for channel '{channel_name}': {e}")
                    channels[channel_name] = 'Error accessing Redis'
        
        await redis_conn.aclose()
        
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error in check_channels: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error occurred")
    finally:
        logger.setLevel(logging.INFO)
   
    return templates.TemplateResponse("partials/multiple_channel_info.html", {"request": request, "channels": channels})

@app.post("/flush_redis_channels/{flow_name}")
async def flush_redis_channels(flow_name: str = Path(..., description="The name of the flow to flush")):
    redis_url = get_redis_url()
    redis_conn = Redis.from_url(redis_url, decode_responses=True)
    
    flow_channels = {
        "scraping": ["scrape_sources", "raw_contents_queue"],
        "embedding": ["contents_without_embedding_queue", "contents_with_embeddings"],
        "entity_extraction": ["contents_without_entities_queue", "contents_with_entities_queue"],
        "geocoding": ["contents_without_geocoding_queue", "contents_with_geocoding_queue"],
        "semantics": ["contents_without_tags_queue", "contents_with_tags_queue"],
        "classification": ["contents_without_classification_queue", "contents_with_classification_queue"]
    }
    
    if flow_name not in flow_channels:
        raise HTTPException(status_code=404, detail=f"Invalid flow name: {flow_name}")
    
    flushed_channels = []
    for channel_name in flow_channels[flow_name]:
        queue_info = config.redis_queues.get(channel_name)
        if queue_info:
            await redis_conn.select(queue_info['db'])
            await redis_conn.delete(queue_info['key'])
            flushed_channels.append(channel_name)
    
    await redis_conn.aclose()
    
    return {"message": f"Flushed Redis channels for {flow_name}", "flushed_channels": flushed_channels}

## Scraping Control
@app.post("/trigger_scraping_sequence")
async def trigger_scraping_flow():
    try:
        return {"message": "Scraping flow triggered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger scraping flow: {str(e)}")

@app.post("/trigger_scraping")
async def trigger_scraping():
    try:
        subprocess.run(["python", "flows/orchestration.py"], check=True)
        return {"message": "Scraping flow triggered"}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger scraping flow: {str(e)}")

## Embedding Management
@app.post("/store_embeddings_in_qdrant")
async def store_embeddings_in_qdrant():
    response = await httpx.post(f"{config.SERVICE_URLS['qdrant-service']}/store_embeddings")
    if response.status_code == 200:
        return {"message": "Embeddings storage in Qdrant triggered successfully."}
    else:
        raise HTTPException(status_code=response.status_code, detail="Failed to trigger embeddings storage in Qdrant.")

### Helper Functions

## Redis Operations
async def get_redis_queue_length(redis_db: int, queue_key: str):
    try:
        redis_conn = Redis(host=os.getenv('REDIS_HOST', 'redis'), port=int(os.getenv('REDIS_PORT', 6379)), db=redis_db)
        queue_length = await redis_conn.llen(queue_key)
        return queue_length
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(e)}")

## Data Models
class SearchType(str, Enum):
    TEXT = "text"
    SEMANTIC = "semantic"

@app.post("/clear_redis")
async def clear_redis_data():
    redis_url = get_redis_url()
    if not redis_url:
        raise HTTPException(status_code=500, detail="Could not get Redis URL")
    try:
        redis = Redis.from_url(redis_url, decode_responses=True)
        await redis.flushall()
        await redis.aclose()
        return {"message": "Redis data cleared"}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=f"Invalid Redis URL: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing Redis data: {str(e)}")

async def log_redis_url():
    """Log the Redis URL every second."""
    try:
        redis_url = get_redis_url()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching Redis URL: {str(e)}")

@app.post("/log_redis_url")
async def log_redis_url_endpoint():
    await log_redis_url()
    return {"message": "Redis URL logged"}

def is_number(value):
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False

# Register the custom filter
templates.env.filters['is_number'] = is_number

# Define the custom test
def is_number(value):
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False

# Register the custom test
templates.env.tests['is_number'] = is_number


# Read rejected Geocodes
@app.get("/read_failed_geocodes")
async def read_failed_geocodes():
    redis_conn = await setup_redis_connection()
    failed_geocodes = await redis_conn.lrange('failed_geocodes_queue', 0, -1)
    return {"failed_geocodes": failed_geocodes}