from fastapi import FastAPI, HTTPException, Query
import requests
from pydantic import BaseModel
from typing import List
import importlib
import json

app = FastAPI()

class Article(BaseModel):
    url: str
    headline: str
    paragraphs: List[str]

def get_scraper_config():
    with open("scraper/config.json") as f:
        return json.load(f)

@app.post("/scrape")
def scrape_data(flags: List[str] = Body(...)):
    from fastapi import Bodyc
    config = get_scraper_config()

    for flag in flags:
        try:
            scraper_config = config[flag]
            scraper_module = importlib.import_module(scraper_config['scraper_location'])
            scraped_data = scraper_module.run_scraper()

            # Assuming scraped_data is a list of Article objects
            response = requests.post(
                "http://postgres_service:8000/receive_raw_articles", 
                json={"data": [article.dict() for article in scraped_data]}
            )
            # Handle response
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Scraper for '{flag}' not found")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Scraping completed"}


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}
