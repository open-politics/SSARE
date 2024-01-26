from fastapi import FastAPI, HTTPException
import httpx
import os
from core.utils import load_config
from populate_qdrant_from_postgres import PopulateQdrant
import requests

app = FastAPI()


@app.get("/populate_qdrant")
async def populate_qdrant():
    postgres_data = requests.get("http://postgres_service:8000/articles")
    populate_qdrant = PopulateQdrant()
    populate_qdrant.populate_qdrant()
    return {"message": "Qdrant populated successfully."}
        

@app.get("/search")
async def search(query: str):
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