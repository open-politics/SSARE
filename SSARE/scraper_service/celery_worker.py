from celery import Celery
import json
from celery.utils.log import get_task_logger
import pandas as pd
import subprocess
import logging
from redis import Redis
logging.basicConfig(level=logging.INFO)
logger = get_task_logger(__name__)

celery_app = Celery("worker", backend="redis://redis:6379/9", broker="redis://redis:6379/9")

@celery_app.task
def scrape_data_task():
    logger.info("Received request to scrape data")
    try:
        redis_conn_flags = Redis(host='redis', port=6379, db=0) # For flags

        flags = redis_conn_flags.lrange('scrape_sources', 0, -1)
        flags = [flag.decode('utf-8') for flag in flags]
        logger.info(f"Scraping data for {flags}")

        for flag in flags:
            scrape_single_source.delay(flag)
            logger.info(f"Scraping data for {flag} complete")
        logger.info("Scraping complete")
    except Exception as e:
        logger.error(f"Error in scraping data: {e}")
        raise e

@celery_app.task
def scrape_single_source(flag: str):
    logger.info(f"Single source scraping for {flag}")
    try:
        with open("./scrapers/scrapers_config.json") as file:
            config_json = json.load(file)

        if flag not in config_json["scrapers"]:
            logger.error(f"No configuration found for flag: {flag}")
            return

        script_location = config_json["scrapers"][flag]["location"]
        logger.info(f"Running script for {flag}")

        result = subprocess.run(["python", script_location], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Error running script for {flag}: {result.stderr}")
            return

        df = pd.read_csv(f"/app/scrapers/data/dataframes/{flag}_articles.csv")
        logger.info(df.head(3))

        # add column "source" which is the flag
        df["source"] = flag
        articles = df.to_dict(orient="records")

        redis_conn_articles = Redis(host='redis', port=6379, db=2)  # For articles
        redis_conn_articles.lpush("scraped_data", json.dumps(articles))
        logger.info(f"Pushed {flag} data to Redis")

        return f"Scraped data for {flag} successfully."
    except Exception as e:
        logger.error(f"Error in scraping {flag}: {e}")
