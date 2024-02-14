from fastapi import FastAPI, HTTPException
import httpx
import os
from core.utils import load_config
from redis.asyncio import Redis

### Configuration & Mapping
config = load_config()["postgresql"]

app = FastAPI()

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

@app.get("/health")
async def healthcheck():
    return {"message": "OK"}, 200

@app.get("/check_services")
async def check_services():
    service_statuses = {}
    for service, url in service_urls.items():
        if url != runtime_url:
            try:
                response = await httpx.get(url + "/health", timeout=10.0)  # Set a timeout of 10 seconds
                service_statuses[service] = response.status_code
            except httpx.TimeoutException:
                service_statuses[service] = "timed out"
            except Exception as e:
                service_statuses[service] = str(e)
    return service_statuses, 200


async def get_redis_queue_length(redis_db: int, queue_key: str):
    try:
        redis_conn = Redis(host='redis', port=6379, db=redis_db)
        queue_length = await redis_conn.llen(queue_key)  # Replace 'queue_key' with your specific key for each channel
        await redis_conn.close()
        return queue_length
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Redis error: {str(e)}")

@app.get("/check_channels")
async def check_channels():
    channel_lengths = {}
    for channel, db_info in redis_channel_mappings.items():
        queue_length = await get_redis_queue_length(db_info['db'], db_info['key'])
        channel_lengths[channel] = queue_length
    return channel_lengths
