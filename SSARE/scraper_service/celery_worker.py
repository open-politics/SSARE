from celery import Celery
from typing import List
import json
from redis import Redis


# Configure Redis
redis_conn = Redis(host='redis', port=6379, db=0)

# Configure Celery
celery_app = Celery(
    "worker",
    backend="redis://redis:6379/0",
    broker="redis://redis:6379/0"
)

@celery_app.task
def scrape_data_task(flags: List[str]):
    for flag in flags:
        scrape_single_source.delay(flag)
  
@celery_app.task
def scrape_single_source(flag: str):
    config_json = json.load(open("./scrapers/scrapers_config.json"))
    
    # Check location of script to run
    script_location = config_json["scrapers"][flag]["location"]
    print("Script location:", script_location)
    
    # run script
    import subprocess
    subprocess.run(["python", script_location])
    print("Script run")

    # get data
    import pandas as pd
    df = pd.read_csv(f"data/dataframes/{flag}_articles.csv")
    print("Data loaded")

    redis_conn.rpush('scraped_data', df.to_json(orient='records'))
    