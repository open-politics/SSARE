from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
from redis import Redis
import logging
from collections import Counter
import requests
from prefect import task, flow
from geojson import Feature, FeatureCollection, Point
from fastapi.responses import JSONResponse
from sqlalchemy.orm import selectinload
from sqlalchemy import and_
import cohere
import sys
from core.service_mapping import ServiceConfig
from core.models import Article, Articles, ArticleEntity, ArticleTag, Entity, EntityLocation, Location, Tag, NewsArticleClassification
from core.adb import get_session
from core.utils import logger

config = ServiceConfig()


async def lifespan(app):
    logger.info("Starting lifespan")
    yield

app = FastAPI(lifespan=lifespan)

co = cohere.Client(config.COHERE_API_KEY)

@app.post("/rerank")
async def rerank(query: str, documents: List[str], top_n: int = None, return_documents: bool = True):
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
        raise HTTPException(status_code=500, detail="Error in reranking")
