from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from typing import List
from redis.asyncio import Redis
from core.models import ArticleBase
from core.utils import load_config
import httpx


app = FastAPI()

model = SentenceTransformer('jinaai/jina-embeddings-v2-base-en')


from core.models import ArticleBase

@app.post("/create_embeddings")
async def create_embeddings(articles: List[ArticleBase]):
    try:
        embeddings = model.encode([article.headline + " ".join(article.paragraphs) for article in articles])
        embeddings_list = embeddings.tolist()

        # Send embeddings to qdrant_service for storage
        async with httpx.AsyncClient() as client:
            response = await client.post("http://qdrant_service:8000/store_embeddings", json={
                "articles": [article.model_dump() for article in articles],
                "embeddings": embeddings_list
            })
            response.raise_for_status()

        return {"message": "Embeddings created successfully and sent for storage."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


