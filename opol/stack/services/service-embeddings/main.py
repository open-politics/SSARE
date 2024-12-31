import json
import logging
import nltk
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from redis import Redis
from fastembed import TextEmbedding
from typing import List
from core.models import Content, ContentChunk
from core.service_mapping import ServiceConfig
from core.utils import get_redis_url, logger
from prefect import flow, task
from prefect.client import get_client
import asyncio
from prefect.deployments import run_deployment

nltk.download('punkt')

model = TextEmbedding(model="all-MiniLM-L6-v2") 

async def lifespan(app):
    yield

app = FastAPI(lifespan=lifespan)
config = ServiceConfig()

logger.error("Initializing Ray")

class EmbeddingRequest(BaseModel):
    batch_size: int = 100

class QueryEmbeddingRequest(BaseModel):
    query: str

@app.get("/healthz")
async def healthcheck():
    return {"message": "NLP Service Running"}, 200

@app.get("/generate_query_embeddings")
def generate_query_embedding(query: str):
    try:
        model = TextEmbedding(model="jinaai/jina-embeddings-v2-base-en")
        embeddings = model.embed(query)
        embeddings_list = [embedding.tolist() for embedding in embeddings]
        embeddings = embeddings_list[0]
        print(f"Generated embeddings for query: {query}, Embeddings Length: {len(embeddings)}")
        return {"embeddings": embeddings}
    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/generate_embeddings")
async def generate_embeddings(request: EmbeddingRequest):
    try:
        print(f"Generating embeddings with batch size: {request.batch_size}")
        await run_deployment(
            name="generate-embeddings-deployment",
            parameters={"batch_size": request.batch_size}
        )
        
        return {"message": "Embeddings generation process initiated successfully"}
    except Exception as e:
        print(f"Error generating embeddings: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))