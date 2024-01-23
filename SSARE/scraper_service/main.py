from fastapi import FastAPI, HTTPException, Query
import requests
from pydantic import BaseModel
from typing import List
import importlib
import json
from fastapi import Body
from celery_worker import scrape_data_task

app = FastAPI()

class Article(BaseModel):
    url: str
    headline: str
    paragraphs: List[str]


@app.post("/trigger_scraping")
async def trigger_scraping():
    task = scrape_data_task.delay()
    return {"message": "Scraping started", "task_id": task.id}


def get_scraper_config():
    with open("./scrapers/config.json") as f:
        return json.load(f)

@app.post("/scrape")
def scrape_data(flags: List[str] = Body(...)):

    for flag in flags:
        


@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok"}
