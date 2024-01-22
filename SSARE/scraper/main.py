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
def scrape_data():
    from importlib import import_module
    import requests
    import json
    

    response = requests.get("http://scraper_service:8000/scrape")
    data = response.json()['data']

    def call_postgres_for_flags(data):
        flags = []
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

    for scraper_name, scraper_details in config["scrapers"].items():
        if scraper_name in call_postgres_for_flags(data):
            print(f"Scraper {scraper_name} needs to be run")
            dataframe = run_scraper(scraper_name, scraper_details["location"])
            send_to_postgres(dataframe)
            update_scraper_config(config)
            return True

