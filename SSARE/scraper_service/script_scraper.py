import json
import os
import pandas as pd
import logging
from redis.asyncio import Redis
from pydantic import ValidationError
from prefect import task, flow
from prefect_ray.task_runners import RayTaskRunner
from core.models import Content
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from core.db import engine
from core.utils import logger
import asyncio
from datetime import datetime

@task
async def load_config(config_file="./scrapers/scrapers_config.json"):
    if not os.path.exists(config_file):
        logger.warning(f"Configuration file not found: {config_file}. Creating an empty file.")
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        with open(config_file, "w") as file:
            json.dump({"scrapers": {}}, file)
    with open(config_file) as file:
        return json.load(file)
    
@task
async def load_csv_data(csv_file):
    try:
        if os.path.getsize(csv_file) == 0:
            logger.warning(f"CSV file is empty: {csv_file}. Skipping article processing.")
            return None
        df = pd.read_csv(csv_file)
        # Replace NaN values with empty strings
        df = df.fillna('')
        return df
    except (FileNotFoundError, pd.errors.EmptyDataError) as e:
        logger.warning(f"Error loading CSV file: {csv_file}. {e}. Skipping article processing.")
        return None

@task
async def run_scraper_script(script_location):
    process = await asyncio.create_subprocess_exec(
        "python", script_location,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        logger.error(f"Scraper script error: {stderr.decode()}")
        return None
    return stdout.decode()

@task
async def process_contents_to_model(contents, flag):
    processed_contents = []
    for content_data in contents:
        try:
            content = Content(
                url=str(content_data['url']),
                title=str(content_data['headline']), 
                text_content=str(content_data['paragraphs']), 
                source=flag,
                content_type="article",
                insertion_date=datetime.utcnow().isoformat()
            )
            processed_contents.append(content)
        except ValidationError as e:
            logger.error(f"Validation error for content from {flag}: {str(e)}")
    return processed_contents

@task
async def save_contents_to_redis(contents, flag):
    redis_conn = Redis(host='redis', port=6379, db=1, decode_responses=True)
    for content in contents:
        try:
            content_data = {
                "url": content.url,
                "title": content.title,
                "text_content": content.text_content,
                "source": flag,
                "content_type": content.content_type,
                "insertion_date": content.insertion_date
            }
            await redis_conn.rpush('raw_contents_queue', json.dumps(content_data))
        except Exception as e:
            logger.error(f"Error saving content to Redis: {str(e)}")
    await redis_conn.aclose()
    logger.info("Contents saved to Redis")

@task
async def scrape_source_by_script_for_flag(flag: str):
    logger.info(f"Scraping started for source: {flag}")
    try:
        config_json = await load_config()
        if flag not in config_json["scrapers"]:
            logger.warning(f"No scraper configuration found for flag: {flag}. Skipping scraping.")
            return None
        script_location = config_json["scrapers"][flag]["location"]
        result = await run_scraper_script(script_location)
        if result is None:
            return None
        csv_file = f"/app/scrapers/data/dataframes/{flag}_articles.csv"
        df = await load_csv_data(csv_file)
        if df is None:
            return None
        contents = df.to_dict(orient="records")

        return contents
    except Exception as e:
        logger.error(f"Error in scraping for {flag}: {str(e)}")
        raise e

@flow(task_runner=RayTaskRunner())
async def scrape_sources_flow(flags):
    redis_conn = None
    try:
        for flag in flags:
            try:
                redis_conn = Redis(host='redis', port=6379, db=1, decode_responses=True)
                await redis_conn.set('scrapers_running', '1')
                contents = await scrape_source_by_script_for_flag(flag)
                logger.warning(f"Scraped {len(contents)} contents for {flag}")
                if contents is None:
                    continue
                processed_contents = await process_contents_to_model(contents, flag)
                logger.warning(f"Processed {len(processed_contents)} contents for {flag}")
                await save_contents_to_redis(processed_contents, flag)
                # Example with initial first characters of the first content
                logger.warning(f"First content: {processed_contents[0].title[:10]}")
                await redis_conn.set('scrapers_running', '0')
                await redis_conn.aclose()
            except Exception as e:
                logger.error(f"Error in scraping for {flag}: {str(e)}")
                continue
    except Exception as e:
        logger.error(f"Error in scrape_sources_flow: {str(e)}")
    finally:
        if redis_conn:
            await redis_conn.aclose()
