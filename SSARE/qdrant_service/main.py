from fastapi import FastAPI, HTTPException
import httpx
import os
from typing import List
from core.utils import load_config
from populate_qdrant_from_postgres import PopulateQdrant
import requests
from core.models import ArticleBase, ArticleModel
from qdrant_client import QdrantClient
from redis import Redis
import uuid

app = FastAPI()

qdrant_client = QdrantClient(host='qdrant_service', port=6333)
collection_name = 'articles'

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
    

# get articles from postgres and create embeddings
@app.post("/store_embeddings")
async def store_embeddings(articles: List[ArticleBase], embeddings: List[List[float]]):
    try:
        # Store embeddings in Qdrant
        for article, embedding in zip(articles, embeddings):
            qdrant_client.upsert(
                collection_name=collection_name,
                points=[{
                    "id": article.url,  # Assuming URLs are unique identifiers
                    "vector": embedding,
                    "payload": article.model_dump()
                }]
            )

        # Send articles and embeddings to postgres_service for storage
        async with httpx.AsyncClient() as client:
            response = await client.post("http://postgres_service:8000/store_articles_with_embeddings", json={
                "articles": [article.model_dump() for article in articles],
                "embeddings": embeddings
            })
            response.raise_for_status()

        return {"message": "Embeddings and articles stored in Qdrant and PostgreSQL successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))