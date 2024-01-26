from fastapi import FastAPI, HTTPException
import httpx
import os
from core.utils import load_config
from populate_qdrant_from_postgres import PopulateQdrant
import requests
from core.models import ArticleBase

app = FastAPI()


@app.get("/healthcheck")
async def healthcheck():
    return {"message": "OK"}


@app.get("/populate_qdrant")
async def populate_qdrant():
    postgres_data = requests.get("http://postgres_service:8000/articles")
    populate_qdrant = PopulateQdrant()
    populate_qdrant.populate_qdrant()
    return {"message": "Qdrant populated successfully."}
        

# get articles from postgres and create embeddings
@app.post("/send_to_nlp_for_embeddings")
async def send_to_nlp_for_embeddings():
    try:
        articles = requests.get("http://postgres_service:5432/articles")
        # Create embeddings
        await httpx.post("http://nlp_service:0420/create_embeddings", json=articles.json())
        return {"message": "Embeddings created successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    

# get articles with embeddings and store into postgres and qdrant
@app.post("/store_processed_articles")
async def store_processed_articles():
    try:
        # Store embeddings
        await httpx.post("http://postgres_service:8000/store_articles_with_embeddings")
        # Populate Qdrant
        await httpx.get("http://qdrant_service:8000/populate_qdrant")
        return {"message": "Articles stored successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))