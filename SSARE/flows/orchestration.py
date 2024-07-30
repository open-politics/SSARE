from prefect import task, flow, get_run_logger
import httpx
from prefect.deployments import Deployment
from prefect.task_runners import SequentialTaskRunner
import asyncio

runtime_url = "http://main_core_app:8089"

service_urls = {
    "main_core_app": runtime_url,
    "postgres_service": "http://postgres_service:5434",
    "nlp_service": "http://nlp_service:0420",
    "geo_service": "http://geo_service:3690",
    "scraper_service": "http://scraper_service:8081",
    "entity_service": "http://entity_service:1290", 
}

@task
async def produce_flags(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{service_urls['postgres_service']}/flags")
    return response.status_code == 200

@task
async def create_scrape_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['scraper_service']}/create_scrape_jobs", timeout=120)
    return response.status_code == 200

@task
async def store_raw_articles(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['postgres_service']}/store_raw_articles")
    return response.status_code == 200

@task
async def deduplicate_articles(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['postgres_service']}/deduplicate_articles")
    return response.status_code == 200

@task
async def create_embedding_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['postgres_service']}/create_embedding_jobs")
    return response.status_code == 200

@task
async def generate_embeddings(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['nlp_service']}/generate_embeddings", timeout=400)
    return response.status_code == 200

@task
async def store_articles_with_embeddings(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['postgres_service']}/store_articles_with_embeddings")
    return response.status_code == 200


@task
async def create_entity_extraction_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['postgres_service']}/create_entity_extraction_jobs", timeout=400)
    return response.status_code == 200

@task
async def extract_entities(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['entity_service']}/extract_entities", timeout=400)
    return response.status_code == 200


@task
async def store_articles_with_entities(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['postgres_service']}/store_articles_with_entities")
    return response.status_code == 200

@task
async def create_geocoding_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['postgres_service']}/create_geocoding_jobs", timeout=400)
    return response.status_code == 200

@task
async def geocode_articles(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{service_urls['geo_service']}/geocode_articles", timeout=400)
    return response.status_code == 200

@flow(task_runner=SequentialTaskRunner()) 
async def scraping_flow(): 
    flags_result = await produce_flags()
    if not flags_result: 
        raise ValueError("Failed to produce flags.")
    
    scrape_result = await create_scrape_jobs()
    if not scrape_result:
        raise ValueError("Failed to create scrape jobs.")
    
    store_raw_result = await store_raw_articles()
    if not store_raw_result:
        raise ValueError("Failed to store raw articles.")
    
    deduplicate_result = await deduplicate_articles()
    if not deduplicate_result:
        raise ValueError("Failed to deduplicate articles.")
    
    embedding_jobs_result = await create_embedding_jobs()
    if not embedding_jobs_result:
        raise ValueError("Failed to create embedding jobs.")
    
    generate_embeddings_result = await generate_embeddings()
    if not generate_embeddings_result:
        raise ValueError("Failed to generate embeddings.")
    
    store_embeddings_result = await store_articles_with_embeddings()
    if not store_embeddings_result:
        raise ValueError("Failed to store articles with embeddings.")
    
    extraction_jobs = await create_entity_extraction_jobs()
    if not extraction_jobs:
        raise ValueError("Failed to create entity extraction jobs")

    entity_extraction_result = await extract_entities()
    if not entity_extraction_result:
        raise ValueError("Failed to extract entities.")
    
    store_entities_result = await store_articles_with_entities()
    if not store_entities_result:
        raise ValueError("Failed to store articles with entities.")
    
    create_geocoding_result = await create_geocoding_jobs()
    if not create_geocoding_result:
        raise ValueError("Failed to create geocoding jobs.")

    geocode_result = await geocode_articles()
    if not geocode_result:
        raise ValueError("Failed to geocode articles.")