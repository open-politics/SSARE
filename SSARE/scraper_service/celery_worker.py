from celery import Celery
import json
from celery.utils.log import get_task_logger
import pandas as pd
import subprocess
import logging
from redis.asyncio import Redis
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
        # Asynchronous Redis connection for flags
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
    logger.info(f"Single source scraping for {flag}")
    try:
        # Load scraper configuration from JSON file
        with open("./scrapers/scrapers_config.json") as file:
            config_json = json.load(file)

        # Check if the flag has a corresponding scraper configuration
        if flag not in config_json["scrapers"]:
            logger.error(f"No configuration found for flag: {flag}")
            return

        # Get the location of the scraper script
        script_location = config_json["scrapers"][flag]["location"]
        logger.info(f"Running script for {flag}")

        # Run the scraper script as a subprocess
        result = subprocess.run(["python", script_location], capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(f"Error running script for {flag}: {result.stderr}")
            return

        # Read the scraped data from CSV to a DataFrame
        df = pd.read_csv(f"/app/scrapers/data/dataframes/{flag}_articles.csv")
        logger.info(df.head(3))

        # Add a 'source' column to the DataFrame with the flag
        df["source"] = flag
        articles = df.to_dict(orient="records")

        # Asynchronous Redis connection for articles
        redis_conn_articles = Redis(host='redis', port=6379, db=1)

        # Push scraped articles to Redis
        redis_conn_articles.lpush("raw_articles_queue", json.dumps(articles))
        logger.info(f"Pushed {flag} data to Redis")

        return f"Scraped data for {flag} successfully."
    except Exception as e:
        logger.error(f"Error in scraping {flag}: {e}")