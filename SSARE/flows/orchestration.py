# from prefect import task, flow, get_run_logger
import httpx
import asyncio
from redis.asyncio import Redis
from core.service_mapping import ServiceConfig

config = ServiceConfig()


async def setup_redis_connection():
    return Redis(host='redis', port=6379, db=1, decode_responses=True)

#@task
async def produce_flags(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{config.service_urls['postgres_service']}/flags")
    return response.status_code == 200

#@task
async def create_scrape_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['scraper_service']}/create_scrape_jobs", timeout=700)
    return response.status_code == 200

#@task
async def store_raw_articles(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_raw_articles")
    return response.status_code == 200

#@task
async def deduplicate_articles(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/deduplicate_articles")
    return response.status_code == 200

#@task
async def create_embedding_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_embedding_jobs")
    return response.status_code == 200

#@task
async def generate_embeddings(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['embedding_service']}/generate_embeddings", params={"batch_size": batch_size}, timeout=700)
    return response.status_code == 200

#@task
async def store_articles_with_embeddings(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_articles_with_embeddings")
    return response.status_code == 200


#@task
async def create_entity_extraction_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_entity_extraction_jobs", timeout=700)
    return response.status_code == 200

#@task
async def extract_entities(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['entity_service']}/extract_entities", params={"batch_size": batch_size}, timeout=700)
    return response.status_code == 200


#@task
async def store_articles_with_entities(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_articles_with_entities")
    return response.status_code == 200

#@task
async def create_geocoding_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_geocoding_jobs", timeout=700)
    return response.status_code == 200

#@task
async def geocode_articles(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['geo_service']}/geocode_articles", params={"batch_size": batch_size}, timeout=700)
    return response.status_code == 200
    
#@task 
async def store_articles_with_geocoding(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_articles_with_geocoding")
    return response.status_code == 200

#@task
async def create_classification_jobs(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_classification_jobs", timeout=700)
    return response.status_code == 200

#@task
async def classify_articles(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['classification_service']}/classify_articles", params={"batch_size": batch_size}, timeout=700)
    return response.status_code == 200

#@task
async def store_articles_with_classification(raise_on_failure=True):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_articles_with_classification")
    return response.status_code == 200


#@flow
async def scraping_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await produce_flags()
        await create_scrape_jobs()
        await store_raw_articles()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

#@flow
async def embedding_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await deduplicate_articles()
        await create_embedding_jobs()
        await generate_embeddings()
        await store_articles_with_embeddings()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

#@flow
async def entity_extraction_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await create_entity_extraction_jobs()
        await extract_entities()
        await store_articles_with_entities()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

#@flow
async def geocoding_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await create_geocoding_jobs()
        await geocode_articles()
        await store_articles_with_geocoding()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

#@flow
async def classification_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await create_classification_jobs()
        await classify_articles()
        await store_articles_with_classification()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

# This function will be called from app/main.py
async def run_flow(flow_name: str):
    flows = {
        "scraping": scraping_flow,
        "embedding": embedding_flow,
        "entity_extraction": entity_extraction_flow,
        "geocoding": geocoding_flow,
        "classification": classification_flow
    }
    
    if flow_name not in flows:
        raise ValueError(f"Unknown flow: {flow_name}")
    
    await flows[flow_name]()


#@flow() 
async def scraping_flow(): 
    redis_conn = await setup_redis_connection()

    await redis_conn.set('Orchestration in progress', '1')

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

    store_geocoding_result = await store_articles_with_geocoding()
    if not store_geocoding_result:
        raise ValueError("Failed to store articles with geocoding.")

    create_classification_result = await create_classification_jobs()
    if not create_classification_result:
        raise ValueError("Failed to create classification jobs.")

    classify_result = await classify_articles()
    if not classify_result:
        raise ValueError("Failed to classify articles.")
    
    store_classification_result = await store_articles_with_classification()
    if not store_classification_result:
        raise ValueError("Failed to store articles with classification.")
    
    await redis_conn.set('Orchestration complete', '0')