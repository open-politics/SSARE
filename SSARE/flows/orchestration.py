# from prefect import task, flow, get_run_logger
import httpx
import asyncio
from redis.asyncio import Redis
from core.service_mapping import ServiceConfig

config = ServiceConfig()

async def setup_redis_connection():
    return Redis(host='redis', port=6379, db=1, decode_responses=True)

async def produce_flags(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.get(f"{config.service_urls['postgres_service']}/flags")
    return response.status_code == 200

async def create_scrape_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['scraper_service']}/create_scrape_jobs", timeout=700)
    return response.status_code == 200

async def store_raw_contents(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_raw_contents")
    return response.status_code == 200

async def deduplicate_contents(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/deduplicate_contents")
    return response.status_code == 200

async def create_embedding_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_embedding_jobs")
    return response.status_code == 200

async def generate_embeddings(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['embedding_service']}/generate_embeddings", params={"batch_size": batch_size}, timeout=700)
    return response.status_code == 200

async def store_contents_with_embeddings(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_contents_with_embeddings")
    return response.status_code == 200

async def create_entity_extraction_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_entity_extraction_jobs", timeout=700)
    return response.status_code == 200

async def extract_entities(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['entity_service']}/extract_entities", params={"batch_size": batch_size}, timeout=700)
    return response.status_code == 200

async def store_contents_with_entities(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_contents_with_entities")
    return response.status_code == 200

async def create_geocoding_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_geocoding_jobs", timeout=700)
    return response.status_code == 200

async def geocode_contents(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['geo_service']}/geocode_contents", params={"batch_size": batch_size}, timeout=700)
    return response.status_code == 200

async def store_contents_with_geocoding(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_contents_with_geocoding")
    return response.status_code == 200

async def create_classification_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_classification_jobs", timeout=700)
    return response.status_code == 200

async def classify_contents(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['classification_service']}/classify_contents", params={"batch_size": batch_size}, timeout=700)
    return response.status_code == 200

async def store_contents_with_classification(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_contents_with_classification")
    return response.status_code == 200

async def scraping_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await produce_flags()
        await create_scrape_jobs()
        await store_raw_contents()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

async def embedding_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await deduplicate_contents()
        await create_embedding_jobs()
        await generate_embeddings()
        await store_contents_with_embeddings()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

async def entity_extraction_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await create_entity_extraction_jobs()
        await extract_entities()
        await store_contents_with_entities()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

async def geocoding_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await create_geocoding_jobs()
        await geocode_contents()
        await store_contents_with_geocoding()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

async def classification_flow():
    redis_conn = await setup_redis_connection()
    await redis_conn.set('Orchestration in progress', '1')

    try:
        await create_classification_jobs()
        await classify_contents()
        await store_contents_with_classification()
    finally:
        await redis_conn.set('Orchestration in progress', '0')

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
