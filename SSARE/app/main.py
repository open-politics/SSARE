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
from pydantic import BaseModel
from enum import Enum
import logging
from core.service_mapping import ServiceConfig
import asyncio
import subprocess
from flows.orchestration import (
    deduplicate_contents, create_embedding_jobs, generate_embeddings,
    store_contents_with_embeddings, create_entity_extraction_jobs,
    extract_entities, store_contents_with_entities,
    create_geocoding_jobs, geocode_contents,
    produce_flags, create_scrape_jobs, store_raw_contents, store_contents_with_geocoding,
    create_classification_jobs, classify_contents, store_contents_with_classification
)
from flows.orchestration import run_flow
from fastapi import Path


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
    try:
        postgres_service_url = f"{config.service_urls['postgres_service']}/contents"
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
            logger.info("Response for search was successful")
        else:
            contents = []     
            logger.info("Response for search was not successful")

        if "HX-Request" in request.headers:
            return templates.TemplateResponse("partials/contents_list.html", {"request": request, "contents": contents})
        else:
            return templates.TemplateResponse("index.html", {"request": request, "search_query": query})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch contents: {str(e)}")

@app.post("/trigger_scraping_sequence")
async def trigger_scraping_flow():
    logger.info("Triggering scraping flow")
    try:
        asyncio.create_task(run_flow("scraping"))
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
    
@app.get("/check_channels/{flow_name}")
async def check_channels(request: Request, flow_name: str):
    redis_conn = Redis(host=config.service_urls['redis'].split('://')[1].split(':')[0], 
                       port=int(config.REDIS_PORT), 
                       decode_responses=True)
    
    flow_channels = {
        "status": {"Orchestration in progress"},
        "scrapers_running": {"scrapers_running"},
        "scraping": ["scrape_sources", "raw_contents_queue"],
        "embedding": ["contents_without_embedding_queue", "contents_with_embeddings"],
        "entity_extraction": ["contents_without_entities_queue", "contents_with_entities_queue"],
        "geocoding": ["contents_without_geocoding_queue", "contents_with_geocoding_queue"],
        "semantics": ["contents_without_tags_queue", "contents_with_tags_queue"],
        "classification": ["contents_without_classification_queue", "contents_with_classification_queue"]
    }
    
    if flow_name not in flow_channels:
        raise HTTPException(status_code=404, detail=f"Invalid flow name: {flow_name}")
    
    channels = {}
    for channel_name in flow_channels[flow_name]:
        queue_info = config.redis_queues.get(channel_name)
        if queue_info:
            await redis_conn.select(queue_info['db'])
            if channel_name == 'Orchestration in progress':
                value = await redis_conn.get(queue_info['key'])
                channels[channel_name] = 'Active' if value == '1' else 'Inactive'
            elif channel_name == 'scrapers_running':
                value = await redis_conn.get(queue_info['key'])
                channels[channel_name] = 'Active' if value == '1' else 'Inactive'
            else:
                channels[channel_name] = await redis_conn.llen(queue_info['key'])
    
    await redis_conn.aclose()
    
    return templates.TemplateResponse("partials/multiple_channel_info.html", {"request": request, "channels": channels})

@app.post("/flush_redis_channels/{flow_name}")
async def flush_redis_channels(flow_name: str = Path(..., description="The name of the flow to flush")):
    redis_conn = Redis(host=config.service_urls['redis'].split('://')[1].split(':')[0], 
                       port=int(config.REDIS_PORT), 
                       decode_responses=True)
    
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

@app.post("/trigger_flow/{flow_name}")
async def trigger_flow(flow_name: str):
    logger.info(f"Triggering {flow_name}")
    try:
        asyncio.create_task(run_flow(flow_name))
        return {"message": f"{flow_name} triggered"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger {flow_name}: {str(e)}")

@app.get("/service_health", response_class=HTMLResponse)
async def service_health(request: Request):
    health_status = {}
    services_to_check = [
        "main_core_app",
        "postgres_service",
        "embedding_service",
        "scraper_service",
        "r2r",
        "rag_service",
        "entity_service",
        "geo_service",
        "ollama",
        "liteLLM",
        "classification_service"
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
async def trigger_step(step_name: str, batch_size: int = Query(50, ge=1, le=100)):
    step_functions = {
        "produce_flags": produce_flags,
        "create_scrape_jobs": create_scrape_jobs,
        "store_raw_contents": store_raw_contents,
        "deduplicate_contents": deduplicate_contents,
        "create_embedding_jobs": create_embedding_jobs,
        "generate_embeddings": lambda: generate_embeddings(batch_size=batch_size),
        "store_contents_with_embeddings": store_contents_with_embeddings,
        "create_entity_extraction_jobs": create_entity_extraction_jobs,
        "extract_entities": lambda: extract_entities(batch_size=batch_size),
        "store_contents_with_entities": store_contents_with_entities,
        "create_geocoding_jobs": create_geocoding_jobs,
        "geocode_contents": lambda: geocode_contents(batch_size=batch_size),
        "store_contents_with_geocoding": store_contents_with_geocoding,
        "create_classification_jobs": create_classification_jobs,
        "classify_contents": lambda: classify_contents(batch_size=batch_size),
        "store_contents_with_classification": store_contents_with_classification
    }
    
    if step_name not in step_functions:
        raise HTTPException(status_code=400, detail="Invalid step name")
    
    try:
        result = await step_functions[step_name]()
        return {"message": f"Step '{step_name}' completed successfully", "batch_size": batch_size if step_name in ["generate_embeddings", "extract_entities", "geocode_contents", "classify_contents"] else None}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute step '{step_name}': {str(e)}")
    
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

class SearchType(str, Enum):
    TEXT = "text"
    SEMANTIC = "semantic"
    
@app.get("/contents", response_class=HTMLResponse)
async def search_contents(
    request: Request,
    search_query: str = Query(None),
    search_type: str = Query("text"),
    skip: int = 0,
    limit: int = 10
):
    postgres_service_url = f"{config.service_urls['postgres_service']}/contents"
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