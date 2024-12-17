from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import joinedload, selectinload
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from fastapi.responses import JSONResponse
from core.service_mapping import ServiceConfig
from core.models import Content, ContentClassification
import numpy as np
import logging
from core.adb import get_session
from core.utils import logger
import cohere as co

# Instantiating App
app = FastAPI()

# Load configuration
config = ServiceConfig()

# Health endpoint
@app.get("/healthz")
async def healthcheck():
    return {"message": "RAG Service Running"}, 200

@app.get("/articles/", response_model=List[dict])
async def read_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_session)):
    logger.info(f"Fetching articles with skip={skip} and limit={limit}")
    statement = select(Content).options(
        selectinload(Content.classification)
    ).offset(skip).limit(limit)
    result = await db.execute(statement)
    contents = result.scalars().all()

    article_data = []
    for index, content in enumerate(contents, start=1):
        article_info = {
            "index": index,
            "headline": content.title,
            "url": content.url,
            "source": content.source,
            "insertion_date": content.insertion_date,
        }
        if content.classification:
            article_info.update({
                "news_category": article.classification.news_category,
                "secondary_categories": content.classification.secondary_categories,
                "keywords": content.classification.keywords,
                "event_type": content.classification.event_type,
            })
        article_data.append(article_info)

    return article_data

@app.post("/rerank")
async def rerank(query: str = Body(...), documents: List[str] = Body(...), top_n: int = 10, return_documents: bool = True):
    try:
        response = co.rerank(
            model="rerank-english-v3.0",
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=return_documents
        )
        return JSONResponse(content=response.dict())
    except Exception as e:
        logger.error(f"Error in reranking: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error during reranking")
