from pydantic import BaseModel
from typing import List, Dict
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
import requests
from core.utils import load_config
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import insert
from core.models import ArticleBase, ArticlesWithEmbeddings
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
class ProcessedArticleModel(Base):
    __tablename__ = 'processed_articles'
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, index=True)
    headline = Column(String)
    paragraphs = Column(Text)
    source = Column(String, nullable=True)
    embedding = Column(Text)  # Storing the embedding as JSON


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

    engine = create_async_engine(f'postgresql+asyncpg://{user}:{password}@{host}/{database_name}?ssl=False')
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

@app.get('/articles', response_model=List[ArticleBase])
async def get_articles():
    async with app.state.db() as session:
        result = await session.execute(select(ArticleModel))
        articles = result.scalars().all()
        return jsonable_encoder(articles)
    

@app.post("/store_articles_with_embeddings")
async def store_articles_with_embeddings(articles: List[ArticleBase], embeddings: List[List[float]]):
    try:
        async with app.state.db() as session:
            for article, embedding in zip(articles, embeddings):
                # Convert embedding to JSON
                embedding_json = json.dumps(embedding)
                # Create a new ProcessedArticleModel instance
                processed_article = ProcessedArticleModel(
                    url=article.url,
                    headline=article.headline,
                    paragraphs=json.dumps(article.paragraphs),  # Convert list to JSON
                    source=article.source,
                    embedding=embedding_json
                )
                session.add(processed_article)
            await session.commit()

        return {"message": "Articles with embeddings stored successfully in PostgreSQL."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred: {str(e)}")