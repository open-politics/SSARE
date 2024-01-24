from celery import Celery
import json
from celery.utils.log import get_task_logger
import pandas as pd
import subprocess
import logging
from redis import Redis

logging.basicConfig(level=logging.INFO)
logger = get_task_logger(__name__)


celery_app = Celery("worker", backend="redis://redis:6379/0", broker="redis://redis:6379/0")

@celery_app.task
def scrape_data_task():
    logger.info("Received request to scrape data")
    with Redis(host='redis', port=6379, db=0) as redis_conn:
        flags = redis_conn.lrange('scrape_sources', 0, -1)
        flags = [flag.decode('utf-8') for flag in flags]
        logger.info(f"Scraping data for {flags}")

        for flag in flags:
            logger.info(f"Scraping data for {flag}")
            scrape_single_source.delay(flag)
            logger.info(f"Scraping data for {flag} complete")
        logger.info("Scraping complete")

@celery_app.task
def scrape_single_source(flag: str):
    logger.info(f"Single source scraping for {flag}")
    try:
        with open("./scrapers/scrapers_config.json") as file:
            config_json = json.load(file)
        script_location = config_json["scrapers"][flag]["location"]
        logger.info(f"Running script for {flag}")

        result = subprocess.run(["python", script_location], capture_output=True, text=True)
        if result.returncode != 0:
            logging.error(f"Error running script for {flag}: {result.stderr}")
        else: 
            logger.info(f"Script for {flag} complete")

        df = pd.read_csv(f"data/dataframes/{flag}_articles.csv")
        logging.info(df.head(3))


        with Redis(host='redis', port=6379, db=0) as redis_conn:
            redis_conn.rpush('scraped_data', df.to_json(orient='records'))
            logger.info(f"pushed {flag} data to redis")

        return f"Scraped data for {flag} successfully."
    except Exception as e:
        logging.error(f"Error in scraping {flag}: {e}")
