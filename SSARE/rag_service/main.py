from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from sqlalchemy.orm import joinedload, selectinload
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from fastapi.responses import JSONResponse
from core.service_mapping import ServiceConfig
from core.models import Article, NewsArticleClassification
import numpy as np
import logging
from core.adb import get_session

import cohere as co

app = FastAPI()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config = ServiceConfig()

@app.get("/healthz")
async def healthcheck():
    return {"message": "RAG Service Running"}, 200

@app.get("/articles/", response_model=List[dict])
async def read_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_session)):
    logger.info(f"Fetching articles with skip={skip} and limit={limit}")
    statement = select(Article).options(
        selectinload(Article.classification)
    ).offset(skip).limit(limit)
    result = await db.execute(statement)
    articles = result.scalars().all()

    article_data = []
    for index, article in enumerate(articles, start=1):
        article_info = {
            "index": index,
            "headline": article.headline,
            "url": article.url,
            "source": article.source,
            "insertion_date": article.insertion_date,
        }
        if article.classification:
            article_info.update({
                "news_category": article.classification.news_category,
                "secondary_categories": article.classification.secondary_categories,
                "keywords": article.classification.keywords,
                "event_type": article.classification.event_type,
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
