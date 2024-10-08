import os
import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from sqlmodel import SQLModel, Field, create_engine, Session, select, update
from sqlmodel import Column, JSON
from contextlib import asynccontextmanager
from enum import Enum
import httpx
import math
import pandas as pd
import uuid
from io import StringIO

from fastapi import Query, APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from sqlalchemy import and_, delete, func, insert, or_, text, update
from sqlalchemy import inspect
from sqlalchemy import desc
from sqlalchemy import join
from sqlalchemy import alias, distinct
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session
from typing import AsyncGenerator

from core.adb import engine, get_session, create_db_and_tables
from core.middleware import add_cors_middleware
from core.models import Article, Articles, ArticleEntity, ArticleTag, Entity, EntityLocation, Location, Tag, NewsArticleClassification
from core.service_mapping import config

router = APIRouter()

########################################################################################
## HELPER FUNCTIONS

@router.post("/deduplicate_articles")
async def deduplicate_articles(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article).group_by(Article.id, Article.url).having(func.count() > 1)
            result = await session.execute(query)
            duplicate_articles = result.scalars().all()

        for article in duplicate_articles:
            logger.info(f"Duplicate article: {article.url}")
            await session.delete(article)

        await session.commit()
        return {"message": "Duplicate articles deleted successfully."}
    except Exception as e:
        logger.error(f"Error deduplicating articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))



#### MISC

@router.delete("/delete_all_classifications")
async def delete_all_classifications(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            # Delete all records from the NewsArticleClassification table
            await session.execute(delete(NewsArticleClassification))
            await session.commit()
            logger.info("All classifications deleted successfully.")
            return {"message": "All classifications deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting classifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting classifications")

@router.delete("/delete_all_embeddings")
async def delete_all_embeddings(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            # Delete all embeddings from all articles
            await session.execute(update(Article).values(embeddings=None))
            await session.commit()
            logger.info("All embeddings deleted successfully.")
            return {"message": "All embeddings deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting embeddings: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting embeddings")

@router.get("/articles_csv_quick")
async def get_articles_csv_quick(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article.id, Article.url, Article.headline, Article.source, Article.insertion_date)
            result = await session.execute(query)
            articles = result.fetchall()

        # Create a DataFrame
        df = pd.DataFrame(articles, columns=['id', 'url', 'headline', 'source', 'insertion_date'])

        # Convert DataFrame to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=articles_quick.csv"})

    except Exception as e:
        logger.error(f"Error generating quick CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating quick CSV")
    
async def get_articles_csv(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article)
            result = await session.execute(query)
            articles = result.scalars().all()

        # Convert articles to a list of dictionaries
        articles_data = [article.dict() for article in articles]

        # Create a DataFrame
        df = pd.DataFrame(articles_data)

        # Convert DataFrame to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=articles.csv"})

    except Exception as e:
        logger.error(f"Error generating CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating CSV")

@router.get("/articles_csv_full")
async def get_articles_csv(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article).options(
                selectinload(Article.entities).selectinload(Entity.locations),
                selectinload(Article.tags),
                selectinload(Article.classification)
            )
            result = await session.execute(query)
            articles = result.scalars().all()

        # Convert articles to a list of dictionaries
        articles_data = []
        for article in articles:
            article_dict = {
                "id": str(article.id),
                "url": article.url,
                "headline": article.headline,
                "source": article.source,
                "insertion_date": article.insertion_date.isoformat() if article.insertion_date else None,
                "paragraphs": article.paragraphs,
                "embeddings": article.embeddings.tolist() if article.embeddings is not None else None,
                "entities": [
                    {
                        "id": str(e.id),
                        "name": e.name,
                        "entity_type": e.entity_type,
                        "locations": [
                            {
                                "name": loc.name,
                                "type": loc.type,
                                "coordinates": loc.coordinates.tolist() if loc.coordinates is not None else None
                            } for loc in e.locations
                        ] if e.locations else []
                    } for e in article.entities
                ] if article.entities else [],
                "tags": [
                    {
                        "id": str(t.id),
                        "name": t.name
                    } for t in (article.tags or [])
                ],
                "classification": article.classification.dict() if article.classification else None
            }
            articles_data.append(article_dict)

        # Flatten the data for CSV
        flattened_data = []
        for article in articles_data:
            base_data = {
                "id": article["id"],
                "url": article["url"],
                "headline": article["headline"],
                "source": article["source"],
                "insertion_date": article["insertion_date"],
                "paragraphs": article["paragraphs"],
                "embeddings": article["embeddings"],
            }
            if article["entities"]:
                for entity in article["entities"]:
                    entity_data = {
                        "entity_id": entity["id"],
                        "entity_name": entity["name"],
                        "entity_type": entity["entity_type"],
                        "locations": json.dumps(entity["locations"]),
                    }
                    flattened_data.append({**base_data, **entity_data})
            else:
                flattened_data.append(base_data)

        # Create a DataFrame
        df = pd.DataFrame(flattened_data)

        # Convert DataFrame to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=articles.csv"})

    except Exception as e:
        logger.error(f"Error generating CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating CSV")
