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
from fastapi.responses import JSONResponse
from sqlalchemy.orm import selectinload
from sqlalchemy import and_
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

async def run_test():
    logger.info("Success")

@task
async def run_test_task():
    await run_test()

@flow
async def testing_flow():
    await run_test_task()

@app.get("/rerank")
async def xtest():
    await testing_flow() 
    return JSONResponse(content={"message": "OK"}, status_code=200) 


if __name__ == "__main__":
       testing_flow.serve(name="my-first-deployment")