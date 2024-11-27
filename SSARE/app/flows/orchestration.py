import logging
from prefect import flow, task, serve
import httpx
import asyncio
from redis.asyncio import Redis
from core.service_mapping import ServiceConfig

logger = logging.getLogger(__name__)
config = ServiceConfig()

# ======================
# Task Definitions
# ======================

@task
async def produce_flags(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.get(f"{config.service_urls['postgres_service']}/flags")
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to produce flags")
    return response.status_code == 200

@task
async def create_scrape_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['scraper_service']}/create_scrape_jobs", timeout=700)
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to create scrape jobs")
    return response.status_code == 200

@task
async def store_raw_contents(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_raw_contents")
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to store raw contents")
    return response.status_code == 200

@task
async def deduplicate_contents(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/deduplicate_contents")
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to deduplicate contents")
    return response.status_code == 200

@task
async def create_embedding_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/create_embedding_jobs")
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to create embedding jobs")
    return response.status_code == 200

@task
async def generate_embeddings(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(
            f"{config.service_urls['embedding_service']}/generate_embeddings",
            params={"batch_size": batch_size},
            timeout=700
        )
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to generate embeddings")
    return response.status_code == 200

@task
async def store_contents_with_embeddings(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_contents_with_embeddings")
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to store contents with embeddings")
    return response.status_code == 200

@task
async def create_entity_extraction_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(
            f"{config.service_urls['postgres_service']}/create_entity_extraction_jobs",
            timeout=700
        )
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to create entity extraction jobs")
    return response.status_code == 200

@task
async def extract_entities(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(
            f"{config.service_urls['entity_service']}/extract_entities",
            params={"batch_size": batch_size},
            timeout=700
        )
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to extract entities")
    return response.status_code == 200

@task
async def store_contents_with_entities(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_contents_with_entities")
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to store contents with entities")
    return response.status_code == 200

@task
async def create_geocoding_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(
            f"{config.service_urls['postgres_service']}/create_geocoding_jobs",
            timeout=700
        )
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to create geocoding jobs")
    return response.status_code == 200

@task
async def geocode_contents(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(
            f"{config.service_urls['geo_service']}/geocode_contents",
            params={"batch_size": batch_size},
            timeout=700
        )
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to geocode contents")
    return response.status_code == 200

@task
async def store_contents_with_geocoding(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_contents_with_geocoding")
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to store contents with geocoding")
    return response.status_code == 200

@task
async def create_classification_jobs(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(
            f"{config.service_urls['postgres_service']}/create_classification_jobs",
            timeout=700
        )
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to create classification jobs")
    return response.status_code == 200

@task
async def classify_contents(batch_size: int = 50, raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(
            f"{config.service_urls['classification_service']}/classify_contents",
            params={"batch_size": batch_size},
            timeout=700
        )
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to classify contents")
    return response.status_code == 200

@task
async def store_contents_with_classification(raise_on_failure=True):
    async with httpx.AsyncClient(timeout=1000) as client:
        response = await client.post(f"{config.service_urls['postgres_service']}/store_contents_with_classification")
    if response.status_code != 200 and raise_on_failure:
        raise Exception("Failed to store contents with classification")
    return response.status_code == 200

# ======================
# Flow Definitions
# ======================

@flow(name="save-raw-contents-flow")
async def save_scraped_contents():
    try:
        await store_raw_contents()
    except Exception as e:
        logger.error(f"Error saving scraped contents: {e}")
        raise e

@flow(name="save-contents-with-embeddings-flow")
async def save_contents_with_embeddings_flow():
    try:
        await store_contents_with_embeddings()
    except Exception as e:
        logger.error(f"Error saving contents with embeddings: {e}")
        raise e

@flow(name="save-contents-with-entities-flow")
async def save_contents_with_entities_flow():
    try:
        await store_contents_with_entities()
    except Exception as e:
        logger.error(f"Error saving contents with entities: {e}")
        raise e

@flow(name="save-geocoded-contents-flow")
async def save_geocoded_contents_flow():
    try:
        await store_contents_with_geocoding()
    except Exception as e:
        logger.error(f"Error saving geocoded contents: {e}")
        raise e

@flow(name="create-jobs-flow")
async def create_jobs_flow():
    try:
        # Schedule all job creations
        await create_scrape_jobs()
        await create_embedding_jobs()
        await create_entity_extraction_jobs()
        await create_geocoding_jobs()
        await create_classification_jobs()
    except Exception as e:
        logger.error(f"Error in create_jobs_flow: {e}")
        raise e

# ======================
# Deployment Definitions
# ======================

if __name__ == "__main__":
    serve(
        save_scraped_contents.to_deployment(
            name="save-raw-contents",
            cron="*/10 * * * *"  # Run every 10 minutes
        ),
        save_contents_with_embeddings_flow.to_deployment(
            name="save-contents-with-embeddings",
            cron="*/10 * * * *"  # Run every 10 minutes
        ),
        save_contents_with_entities_flow.to_deployment(
            name="save-contents-with-entities",
            cron="*/20 * * * *"  # Run every 20 minutes
        ),
        save_geocoded_contents_flow.to_deployment(
            name="save-geocoded-contents",
            cron="*/20 * * * *"  # Run every 20 minutes
        ),
        create_jobs_flow.to_deployment(
            name="create-jobs",
            cron="0 */4 * * *"  # Run every 4 hours
        )
    )