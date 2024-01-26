from pydantic import BaseModel
from typing import List, Dict
from fastapi import FastAPI, HTTPException
from fastapi.encoders import jsonable_encoder
from typing import Optional
from fastapi import Query
import requests
from core.utils import load_config
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import insert
from core.models import ArticleBase, ArticlesWithEmbeddings
from sqlalchemy import Column, Integer, String
from sqlalchemy import update
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect
from core.utils import load_config
from redis import Redis
import pandas as pd
from core.models import ArticleBase, ArticleModel, ProcessedArticleModel
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from core.models import ArticleBase
import json
from fastapi import FastAPI
from sqlalchemy import select
from core.models import ArticleBase
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import bindparam
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import bindparam

Base = declarative_base()

# SQLAlchemy model - unprocessed articles
class ArticleModel(Base):
    __tablename__ = 'articles'
    url = Column(String, primary_key=True, index=True)
    headline = Column(String)
    paragraphs = Column(Text)
    source = Column(String, nullable=True)
    embedding = Column(Text)  # Storing the embedding as JSON

    embeddings_created = Column(Integer, default=0)  # 0 = False, 1 = True
    isStored_in_qdrant = Column(Integer, default=0)  # 0 = False, 1 = True

    def model_dump(self):
        return {
            "url": self.url,
            "headline": self.headline,
            "paragraphs": json.loads(self.paragraphs),
            "source": self.source,
            "embedding": json.loads(self.embedding),
            "embeddings_created": self.embeddings_created,
            "isStored_in_qdrant": self.isStored_in_qdrant
        }


# SQLAlchemy model
class ProcessedArticleModel(Base):
    __tablename__ = 'processed_articles'

    url = Column(String, primary_key=True, index=True)
    headline = Column(String)
    paragraphs = Column(Text)
    source = Column(String, nullable=True)
    embedding = Column(Text)  # Storing the embedding as JSON

    embeddings_created = Column(Integer, default=0)  # 0 = False, 1 = True
    isStored_in_qdrant = Column(Integer, default=0)  # 0 = False, 1 = True

    def model_dump(self):
        return {
            "url": self.url,
            "headline": self.headline,
            "paragraphs": json.loads(self.paragraphs),
            "source": self.source,
            "embedding": json.loads(self.embedding),
            "embeddings_created": self.embeddings_created,
            "isStored_in_qdrant": self.isStored_in_qdrant
        }


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
    """
    This function produces flags for the scraper service. It is triggered by an API call.
    It deletes all existing flags in Redis Queue 0 - channel "scrape_sources" and pushes new flags.
    The flag creation mechanism is to be updated, and not hardcoded like now.
    """
    redis_conn_flags.delete("scrape_sources")
    flags = ["cnn",]
    for flag in flags:
        redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@app.get('/articles', response_model=List[ArticleBase])
async def get_articles(
    embeddings_created: Optional[bool] = Query(None),
    isStored_in_Qdrant: Optional[bool] = Query(None),
    skip: int = 0,
    limit: int = 10
    ):

    async with app.state.db() as session:
        query = select(ArticleModel)
        
        if embeddings_created is not None:
            query = query.where(ArticleModel.embeddings_created == embeddings_created)

        if isStored_in_Qdrant is not None:
            query = query.where(ArticleModel.isStored_in_Qdrant == isStored_in_Qdrant)

        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        articles = result.scalars().all()
        
        return jsonable_encoder(articles)

@app.post("/store_raw_articles")
async def store_raw_articles():
    try:
        redis_conn = await Redis(host='redis', port=6379, db=1)
        raw_articles = await redis_conn.lrange('raw_articles_queue', 0, -1)
        await redis_conn.delete('raw_articles_queue')

        async with app.state.db() as session:
            for raw_article in raw_articles:
                article_data = json.loads(raw_article)
                article = ArticleBase(**article_data)
                db_article = ArticleModel(**article.model_dump())
                session.add(db_article)
            await session.commit()

        return {"message": "Raw articles stored successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/store_articles_with_embeddings")
async def store_processed_articles():
    try:
        redis_conn = await Redis(host='redis', port=6379, db=3)
        articles_with_embeddings = await redis_conn.lrange('articles_with_embeddings', 0, -1)
        await redis_conn.delete('articles_with_embeddings')

        articles = []
        embeddings = []
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
                    embedding=embedding_json,
                    embeddings_created=1,  # Set to True
                )
                session.add(processed_article)
            await session.commit()

        return {"message": "Articles with embeddings stored successfully in PostgreSQL."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"An error occurred: {str(e)}")

@app.post("/update_qdrant_flags")
async def update_qdrant_flags(urls: List[str]):
    try:
        async with app.state.db() as session:
            stmt = update(ProcessedArticleModel).\
                where(ProcessedArticleModel.url == bindparam('url')).\
                values(isStored_in_qdrant=True)
            await session.execute(stmt, [{"url": url} for url in urls])
            await session.commit()

        return {"message": "Qdrant flags updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
