from celery import Celery
from typing import List
import json

# Configure Celery
celery_app = Celery(
    "worker",
    backend="redis://localhost:6379/0",
    broker="redis://localhost:6379/0"
)

@celery_app.task
def scrape_data_task(flags: List[str]):
    config_json = json.load(open("./scrapers/scrapers_config.json"))
    
    # Check location of script to run
    script_location = config_json["scrapers"]["cnn"]["location"]
    print("Script location:", script_location)
    
    # run script
    import subprocess
    subprocess.run(["python", script_location])
    print("Script run")

    # get data
    import pandas as pd
    df = pd.read_csv("data/dataframes/cnn_articles.csv")
    print("Data loaded")
    
