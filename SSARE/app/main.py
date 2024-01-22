from fastapi import FastAPI, HTTPException
import httpx
from dotenv import load_dotenv
import os
from core.utils import load_config

app = FastAPI()

config = load_config()["postgresql"]

DATABASE_SERVICE_URL = os.getenv("DATABASE_SERVICE_URL")
SCRAPER_SERVICE_URL = os.getenv("SCRAPER_SERVICE_URL")
PROCESSOR_SERVICE_URL = os.getenv("PROCESSOR_SERVICE_URL")



@app.post("/trigger_scraping")
async def trigger_scraping():
    async with httpx.AsyncClient() as client:
        try:
            # Trigger the scraper service to start scraping
            response = await client.post(SCRAPER_SERVICE_URL)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.post("/check_for_processing")
async def check_for_processing():
    async with httpx.AsyncClient() as client:
        try:
            # Get the flags from the database service to see which sources need scraping
            response = await client.get(DATABASE_SERVICE_URL + "/flags")
            response.raise_for_status()
            flags = response.json().get("flags", [])
            
            # If there are flags, process the respective articles
            if flags:
                process_response = await client.post(PROCESSOR_SERVICE_URL, json={"flags": flags})
                process_response.raise_for_status()
                return process_response.json()
            return {"message": "No articles to process at this time."}
        except httpx.HTTPError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e))

@app.post("/save_processed_articles")
async def save_processed_articles(articles: list):
    async with httpx.AsyncClient() as client:
        try:
            # Save the processed articles to the database
            response = await client.post(DATABASE_SERVICE_URL, json={"articles": articles})
            response.raise_for_status()
            return {"message": "Processed articles saved successfully."}
        except httpx.HTTPError as e:
            raise HTTPException(status_code=e.response.status_code, detail=str(e
