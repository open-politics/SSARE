from fastapi import FastAPI, HTTPException
import httpx
import os
from core.utils import load_config

app = FastAPI()

config = load_config()["postgresql"]


@app.get("/healthcheck")
async def healthcheck():
    return {"message": "OK"}

@app.post("/full_run")
async def full_run():
    try:
        # Produce flags
        await httpx.post("http://scraper_service:5432/flags")
        # Scrape data
        await httpx.post("http://scraper_service:8081/create_scrape_jobs")
        # Create embeddings
        await httpx.post("http://nlp_service:0420/create_embeddings")
        # Store embeddings
        await httpx.post("http://postgres_service:8000/store_embeddings")
        return {"message": "Full run complete."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))