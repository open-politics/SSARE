import json
import os
import pandas as pd
import logging
from redis.asyncio import Redis
from pydantic import ValidationError
from prefect import task, flow
from prefect_ray.task_runners import RayTaskRunner
from core.models import Article, Articles
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from core.db import engine
from core.utils import logger
import asyncio

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
async def process_articles_to_model(articles, flag):
    processed_articles = []
    for article_data in articles:
        try:
            article = Article(
                url=str(article_data['url']),
                headline=str(article_data['headline']),
                paragraphs=str(article_data['paragraphs']),
                source=str(article_data['source']),
            )
            processed_articles.append(article)
        except ValidationError as e:
            logger.error(f"Validation error for article from {flag}: {str(e)}")
    return Articles(articles=processed_articles)

@task
async def save_articles_to_redis(articles, flag):
    redis_conn = Redis(host='redis', port=6379, db=1, decode_responses=True)
    for article in articles:
        try:
            article_data = {
                "url": str(article.url),
                "headline": str(article.headline),
                "paragraphs": str(article.paragraphs),
                "source": flag
            }
            await redis_conn.rpush('raw_articles_queue', json.dumps(article_data))
        except Exception as e:
            logger.error(f"Error saving article to Redis: {str(e)}")
    await redis_conn.aclose()
    logger.info("Articles saved to Redis")

@task
async def process_articles_to_model(articles, flag):
    processed_articles = []
    for article_data in articles:
        try:
            article = Article(
                url=article_data['url'],
                headline=article_data['headline'],
                paragraphs=article_data['paragraphs'],
                source=flag,
            )
            processed_articles.append(article)
        except ValidationError as e:
            logger.error(f"Validation error for article from {flag}: {str(e)}")
    return Articles(articles=processed_articles)

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
        articles = df.to_dict(orient="records")
        return articles
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
                articles = await scrape_source_by_script_for_flag(flag)
                if articles is None:
                    continue
                processed_articles = await process_articles_to_model(articles, flag)
                await save_articles_to_redis(processed_articles.articles, flag)
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