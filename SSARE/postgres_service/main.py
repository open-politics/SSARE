from pydantic import BaseModel
from typing import List, Dict
from fastapi import FastAPI, HTTPException
import requests
from core.utils import load_config
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect
from core.utils import load_config
from redis import Redis
import pandas as pd
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
import json
from fastapi import FastAPI
from sqlalchemy import select
from core.models import ArticleBase
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

# SQLAlchemy model
class ArticleModel(Base):
    __tablename__ = 'articles'
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    headline = Column(String)
    paragraphs = Column(Text)
    # Add a new column for the source if necessary
    source = Column(String, nullable=True)


app = FastAPI()

redis_conn_flags = Redis(host='redis', port=6379, db=0)  # For flags
redis_conn_articles = Redis(host='redis', port=6379, db=2)  # For articles


async def setup_db_connection():
    config = load_config()['postgresql']
    database_name = load_config()['postgresql']['postgres_db']
    table_name = load_config()['postgresql']['postgres_table_name']
    user = load_config()['postgresql']['postgres_user']
    password = load_config()['postgresql']['postgres_password']
    host = load_config()['postgresql']['postgres_host']

    engine = create_async_engine(f'postgresql+asyncpg://{user}:{password}@postgres_service/{database_name}?sslmode=disable')
    return engine

async def close_db_connection(engine):
    # Close PostgreSQL connection
    await engine.dispose()

@asynccontextmanager
async def db_lifespan(app: FastAPI):
    # Before app startup
    engine = await setup_db_connection()
    app.state.db = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield
    # After app shutdown
    await close_db_connection(engine)

app = FastAPI(lifespan=db_lifespan)

@app.get("/flags")
def produce_flags():
    redis_conn_flags.delete("scrape_sources")
    flags = ["cnn",]
    for flag in flags:
        redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}
    
@app.get('/receive_raw_articles')
async def save_raw_articles():
    async with app.state.db() as session:  # Use the async session
        raw_articles = redis_conn_articles.lrange('scraped_data', 0, -1)
        redis_conn_articles.delete('scraped_data')

        articles_to_save = []
        for raw_article in raw_articles:
            article_data = json.loads(raw_article)
            # Deserialize paragraphs if it's stored as JSON string
            paragraphs = json.loads(article_data['paragraphs']) if isinstance(article_data['paragraphs'], str) else article_data['paragraphs']
            article = ArticleModel(
                url=article_data['url'],
                headline=article_data['headline'],
                paragraphs=paragraphs,
                source=article_data['source']
            )
            articles_to_save.append(article)

        session.add_all(articles_to_save)
        await session.commit()

    return {"message": f"{len(articles_to_save)} articles saved"}

@app.get('/articles')
async def get_articles():
    async with app.state.db() as session:
        articles = await session.execute(select(ArticleModel))
        articles = articles.scalars().all()
        return {"articles": articles}
    

@app.post("/store_articles_with_embeddings")
async def store_articles_with_embeddings():
    try:
        # Get embeddings from Redis
        redis_conn_embeddings = Redis(host='redis', port=6379, db=4, decode_responses=True)
        articles = redis_conn_embeddings.keys()
        articles = [article for article in articles]
        embeddings = [redis_conn_embeddings.get(article) for article in articles]
        # Store in PostgreSQL
        async with app.state.db() as session:
            for i, article in enumerate(articles):
                article = ArticleModel(
                    url=article,
                    headline="",
                    paragraphs="",
                    source="",
                    embedding=embeddings[i]
                )
                session.add(article)
            await session.commit()
        return {"message": "Embeddings stored successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))