from fastapi import FastAPI
import requests
from typing import List, Dict
from pydantic import BaseModel


app = FastAPI()

class Article(BaseModel):
    url: str
    headline: str
    paragraphs: List[str]


@app.get("/scrape")
def scrape_data(flags: List[str]):
    from importlib import import_module
    import requests
    import json

    def call_postgres_for_flags(flags):
        response = requests.get("http://postgres_service:8000/flags")
        flags = response.json()['flags']
        # [cnn, zdf, fox]
        return flags
    
    def run_scraper(scraper_name, scraper_location):
        scraper = import_module(scraper_location)
        dataframe = scraper.run_scraper()
        # url, headline, paragraphs
        return dataframe
    
    def get_scraper_config():
        with open("data/scraper_config.json") as f:
            config = json.load(f)
        return config
    
    def update_scraper_config(config):
        with open("data/scraper_config.json", "w") as f:
            json.dump(config, f, indent=4)

    def send_to_postgres(data):
        response = requests.post("http://postgres_service:8000/receive_raw_articles", json={"data": data})
        return response.json()

    config = get_scraper_config()

    for flag in flags:
        scraper_name = config[flag]['scraper_name']
        scraper_location = config[flag]['scraper_location']
        dataframe = run_scraper(scraper_name, scraper_location)
        data = dataframe.to_dict(orient="records")
        send_to_postgres(data)
        config[flag]['last_run'] = "now"
        update_scraper_config(config)

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}

