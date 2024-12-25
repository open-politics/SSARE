from prefect import task
from redis import Redis
import json
from typing import List
from core.models import Content
from core.utils import get_redis_url
from prefect.logging import get_run_logger

@task(name="Save Contents to Redis", retries=3, retry_delay_seconds=60)
def save_contents_to_redis(contents: List[Content]):
    logger = get_run_logger()
    redis_conn = Redis.from_url(get_redis_url(), db=1)
    try:
        for content in contents:
            if content.url not in redis_conn.lrange('raw_contents_queue', 0, -1):
                redis_conn.rpush('raw_contents_queue', content.json())
        logger.info(f"Saved {len(contents)} contents to Redis.")
    except Exception as e:
        logger.error(f"Error saving contents to Redis: {e}")
    finally:
        redis_conn.close()