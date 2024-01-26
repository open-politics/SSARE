from pydantic import BaseModel
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import create_engine, select, update, bindparam
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Text
from redis.asyncio import Redis 
import json
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from core.models import ArticleBase, ArticleModel
from core.utils import load_config
from pydantic import ValidationError

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


Base = declarative_base()

# SQLAlchemy model - unprocessed articles
class ArticleModel(Base):
    """
    This model is used to store unprocessed articles in PostgreSQL after scraping.
    """
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
    """
    This model is used to store processed articles in PostgreSQL after NLP processing.
    """
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
    database_name = config['postgres_db']
    table_name = config['postgres_table_name']
    user = config['postgres_user']
    password = config['postgres_password']
    host = config['postgres_host']

    engine = create_async_engine(f'postgresql+asyncpg://{user}:{password}@{host}/{database_name}?ssl=False')
    return engine

async def close_db_connection(engine):
    # Close PostgreSQL connection
    await engine.dispose()

@asynccontextmanager
async def db_lifespan(app: FastAPI):
    """
    This function is used to setup and close the PostgreSQL connection.
    It is used as a context manager.
    """
    # Before app startup
    engine = await setup_db_connection()
    app.state.db = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield
    # After app shutdown
    await close_db_connection(engine)

app = FastAPI(lifespan=db_lifespan)

@app.get("/flags")
async def produce_flags():
    """
    This function produces flags for the scraper service. It is triggered by an API call.
    It deletes all existing flags in Redis Queue 0 - channel "scrape_sources" and pushes new flags.
    The flag creation mechanism is to be updated, and not hardcoded like now.
    """
    redis_conn_flags.delete("scrape_sources")
    flags = ["cnn",]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@app.get('/articles', response_model=List[ArticleBase])
async def get_articles(
    embeddings_created: Optional[bool] = Query(None),
    isStored_in_Qdrant: Optional[bool] = Query(None),
    skip: int = 0,
    limit: int = 10
    ):
    """
    This function is used to retrieve articles from PostgreSQL.
    It can be used to retrieve all articles, or articles with specific flags.
    """
    async with app.state.db() as session:
        query = select(ArticleModel)
        
        if embeddings_created is not None:
            query = query.where(ArticleModel.embeddings_created == embeddings_created)

        if isStored_in_Qdrant is not None:
            query = query.where(ArticleModel.isStored_in_qdrant == isStored_in_Qdrant)

        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        articles = result.scalars().all()
        
        return jsonable_encoder(articles)

@app.post("/store_raw_articles")
async def store_raw_articles():
    """
    This function is triggered by an API call. It reads from redis queue 1 - channel raw_articles_queue
    and stores the articles in PostgreSQL.
    """
    try:
        redis_conn = await Redis(host='redis', port=6379, db=1)
        raw_articles = await redis_conn.lrange('raw_articles_queue', 0, -1)
        await redis_conn.delete('raw_articles_queue')

        async with app.state.db() as session:
            for raw_article in raw_articles:
                try:
                    article_data = json.loads(raw_article)
                    article = ArticleBase(**article_data)
                    db_article = ArticleModel(**article.model_dump())
                    session.add(db_article)
                except ValidationError as e:
                    logger.error(f"Validation error for article: {e}")
                    # You can also log article_data to see what's wrong
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error: {e}")
                    # Log raw_article here to inspect the malformed JSON

            await session.commit()

        return {"message": "Raw articles stored successfully."}
    except Exception as e:
        logger.error(f"Error storing articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/store_articles_with_embeddings")
async def store_processed_articles():
    """
    This function is triggered by an API call. 
    It reads from redis queue 6 - channel articles_with_embeddings
    and stores the articles in PostgreSQL.
    """
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
    """
    This function is triggered by an API call.
    It updates the isStored_in_qdrant flag for articles in PostgreSQL which have been stored in Qdrant.
    It is used by the qdrant_service.
    """
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
