from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer
from typing import List
from redis.asyncio import Redis
from core.models import ArticleBase

app = FastAPI()

model = SentenceTransformer('paraphrase-distilroberta-base-v1')



@app.post("/create_embeddings")
async def create_embeddings(articles: List[ArticleBase]):
    try:
        # Generate embeddings
        embeddings = model.encode([article.headline + " ".join(article.paragraphs) for article in articles])

        # Push to redis
        redis_conn_embeddings = Redis(host='redis', port=6379, db=4, decode_responses=True)
        try:
            for i, article in enumerate(articles):
                await redis_conn_embeddings.set(article.url, embeddings[i].tolist())
        finally:
            await redis_conn_embeddings.close()

        # Additional logic to handle embeddings
        return {"message": "Embeddings created successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



# @app.post("/create_embeddings")
# async def create_embeddings(articles: List[UnprocessedArticle]):

#     # Generate embeddings
#     embeddings = model.encode([article.headline + " ".join(article.paragraphs) for article in articles])
    
#     # Push to redis
#     redis_conn = Redis(host='redis', port=6379, db=3, decode_responses=True)
#     try:
#         await redis_conn.setex("embedding_cache", 60, "Some value")  # Example for setting a key with an expiry
#         for i, article in enumerate(articles):
#             await redis_conn.set(article.url, embeddings[i].tolist())
#     finally:
#         await redis_conn.close()

#     return {"message": "Embeddings created successfully."}
