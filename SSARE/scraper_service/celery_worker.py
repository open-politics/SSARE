from celery import Celery
import json
from celery.utils.log import get_task_logger
from core.models import ArticleBase
import pandas as pd
import subprocess
import logging
from redis import Redis
from pydantic import ValidationError

""" 
This Script is creating Celery tasks for scraping data from news sources.
It is triggered by the orchestrator service.
The scrapa_daa_task function reads from Redis Queue 0 - channel "scrape_sources" and creates a scraping job for each flag.
It passes a flag as a string argument to the scrape_single_source function.
"""


logging.basicConfig(level=logging.INFO)
logger = get_task_logger(__name__)

celery_app = Celery("worker", backend="redis://redis:6379/9", broker="redis://redis:6379/9")

@celery_app.task
def scrape_data_task():
    """
    This function will be called by the main.py script. It will check the flags in Redis Queue 0 - channel "scrape_sources"
    and create a scraping job for each flag with Celery.
    It passes a flag as a string argument to the scrape_single_source function.
    """
    logger.info("Received request to scrape data")
    try:
        # Synchronous Redis connection for flags
        redis_conn_flags = Redis(host='redis', port=6379, db=0)

        # Retrieve all flags from Redis
        flags = redis_conn_flags.lrange('scrape_sources', 0, -1)
        flags = [flag.decode('utf-8') for flag in flags]
        logger.info(f"Scraping data for {flags}")

        # Trigger scraping for each flag
        for flag in flags:
            scrape_single_source.delay(flag)
            logger.info(f"Scraping data for {flag} complete")
        logger.info("Scraping complete")
    except Exception as e:
        logger.error(f"Error in scraping data: {e}")
        raise e

@celery_app.task
def scrape_single_source(flag: str):
    """
    This function is triggered by the scrape_data_task function. It will run the corresponding scraper script
    for the flag. It will then read the CSV file created by the scraper script 
    and push the data to Redis Queue 1 - channel "raw_articles_queue".
    """
    logger.info(f"Scraping started for source: {flag}")
    try:
        with open("./scrapers/scrapers_config.json") as file:
            config_json = json.load(file)

        if flag not in config_json["scrapers"]:
            logger.error(f"No scraper configuration for flag: {flag}")
            return

        script_location = config_json["scrapers"][flag]["location"]
        result = subprocess.run(["python", script_location], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Scraper script error for {flag}: {result.stderr}")
            return

        df = pd.read_csv(f"/app/scrapers/data/dataframes/{flag}_articles.csv")

        articles = df.to_dict(orient="records")

        redis_conn_articles = Redis(host='redis', port=6379, db=1)

        for article_data in articles:
            try:
                validated_article = ArticleBase(**article_data)
                article_summary = {k: v[:10] if isinstance(v, str) else v for k, v in validated_article.model_dump().items()}
                logger.info(f"Storing article summary: {article_summary}")
                redis_conn_articles.lpush("raw_articles_queue", json.dumps(validated_article.model_dump()))
            except ValidationError as e:
                logger.error(f"Validation error: {e.json()}")

        logger.info(f"Completed scraping for {flag}")
    except Exception as e:
        logger.error(f"Error in scraping for {flag}: {e}")
        raise e