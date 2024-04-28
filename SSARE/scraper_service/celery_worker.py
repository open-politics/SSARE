from celery import Celery
import json
import os
from core.models import ArticleBase
import pandas as pd
import subprocess
import logging
from redis import Redis
from pydantic import ValidationError
from prefect import task, flow
from prefect_ray.task_runners import RayTaskRunner
from prefect.task_runners import ConcurrentTaskRunner, SequentialTaskRunner

""" 
This Script is creating Celery tasks for scraping data from news sources.
It is triggered by the orchestrator service.
The scrapa_daa_task function reads from Redis Queue 0 - channel "scrape_sources" and creates a scraping job for each flag.
It passes a flag as a string argument to the scrape_single_source function.
"""


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

celery_app = Celery("worker", backend="redis://redis:6379/9", broker="redis://redis:6379/9")


@task
def scrape_single_source(flag: str):
    logger.info(f"Scraping started for source: {flag}")
    try:
        config_file = "./scrapers/scrapers_config.json"
        if not os.path.exists(config_file):
            logger.warning(f"Configuration file not found: {config_file}. Creating an empty file.")
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w") as file:
                json.dump({"scrapers": {}}, file)

        with open(config_file) as file:
            config_json = json.load(file)

        if flag not in config_json["scrapers"]:
            logger.warning(f"No scraper configuration found for flag: {flag}. Skipping scraping.")
            return

        script_location = config_json["scrapers"][flag]["location"]
        result = subprocess.run(["python", script_location], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Scraper script error for {flag}: {result.stderr}")
            return

        csv_file = f"/app/scrapers/data/dataframes/{flag}_articles.csv"
        if not os.path.exists(csv_file):
            logger.warning(f"CSV file not found: {csv_file}. Skipping article processing.")
            return

        df = pd.read_csv(csv_file)
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


@flow(task_runner=SequentialTaskRunner())
def scrape_data_task(flags):
    for flag in flags:
        scrape_single_source.submit(flag)
        logger.info(f"Scraping data for {flag} complete")
    logger.info("Scraping complete")
