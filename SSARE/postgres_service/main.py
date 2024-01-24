from pydantic import BaseModel
from typing import List, Dict
from fastapi import FastAPI
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

Base = declarative_base()

class ArticleModel(Base):
    __tablename__ = 'articles'

    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    headline = Column(String)
    paragraphs = Column(Text)  # Assuming paragraphs are stored as a string


app = FastAPI()

redis_conn = Redis(host='redis', port=6379, db=0)

async def setup_db_connection():

    config = load_config()['postgresql']
    database_name = load_config()['postgresql']['postgres_db']
    table_name = load_config()['postgresql']['postgres_table_name']
    user = load_config()['postgresql']['postgres_user']
    password = load_config()['postgresql']['postgres_password']
    host = load_config()['postgresql']['postgres_host']

    engine = create_async_engine(f'postgresql+asyncpg://{user}:{password}@postgres_service/{database_name}')
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
    redis_conn.delete("scrape_sources")
    flags = ["cnn",]

    for flag in flags:
        redis_conn.lpush("scrape_sources", flag)
    
    return {"message": f"Flags produced: {', '.join(flags)}"}
    
@app.get('/receive_raw_articles')
async def save_raw_articles():
    async with app.state.db() as session:  # Use the async session
        raw_articles = redis_conn.lrange('scraped_data', 0, -1)
        redis_conn.delete('scraped_data')

        articles_to_save = []
        for raw_article in raw_articles:
            article_data = json.loads(raw_article)
            for data in article_data:
                article = ArticleModel(
                    url=data['url'],
                    headline=data['headline'],
                    paragraphs=json.dumps(data['paragraphs'])  # Assuming paragraphs is a list
                )
                articles_to_save.append(article)

        session.add_all(articles_to_save)
        await session.commit()

    return {"message": f"{len(articles_to_save)} articles saved"}
