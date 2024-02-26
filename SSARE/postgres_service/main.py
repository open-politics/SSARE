from typing import List, Optional
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import select, Column, Integer, String, Float
from sqlalchemy.sql.expression import update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, sessionmaker
from pydantic import BaseModel
from contextlib import asynccontextmanager
import logging
from redis.asyncio import Redis
from core.utils import load_config

config = load_config()['postgresql']

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLAlchemy Base and Models
Base = declarative_base()

class Article(Base):
    __tablename__ = "articles"
    url = Column(String, primary_key=True)
    headline = Column(String)
    paragraphs = Column(String)  # Assuming JSON stored as string
    source = Column(String)
    embeddings = Column(ARRAY(Float))  # Assuming embeddings as array of floats
    embeddings_created = Column(Integer, default=0)
    stored_in_qdrant = Column(Integer, default=0)

# Pydantic models for request and response validation
class ArticleModel(BaseModel):
    url: str
    headline: str
    paragraphs: str  # JSON string
    source: Optional[str]
    embeddings: Optional[List[float]]
    embeddings_created: int = 0
    stored_in_qdrant: int = 0

class ProcessedArticleModel(ArticleModel):
    pass

# Async Engine and Session
DATABASE_URL = (
    f"postgresql+asyncpg://{config['postgres_user']}:{config['postgres_password']}@"
    f"{config['postgres_host']}/{config['postgres_db']}"
)
engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Redis connections
redis_conn_flags = Redis(host='redis', port=6379, db=0)  # For flags

# Database Dependency
from typing import AsyncGenerator
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


# Application Lifespan Context Manager
@asynccontextmanager
async def startup_and_shutdown():
    logger.info("Starting up: Database and Redis setup")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await redis_conn_flags.ping()
    yield
    logger.info("Shutting down")

app = FastAPI(on_startup=[startup_and_shutdown])

# Health Check Endpoint
@app.get("/health")
async def healthcheck():
    return {"message": "Postgres and Redis Services Running"}

@app.get("/flags")
async def produce_flags():
    await redis_conn_flags.delete("scrape_sources")
    flags = ["cnn"]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@app.get('/articles', response_model=List[ArticleModel])
async def get_articles(embeddings_created: Optional[int] = None, stored_in_qdrant: Optional[int] = None, skip: int = 0, limit: int = 10, session: AsyncSession = Depends(get_session)):
    async with session.begin():
        query = select(Article)
        if embeddings_created is not None:
            query = query.filter(Article.embeddings_created == embeddings_created)
        if stored_in_qdrant is not None:
            query = query.filter(Article.stored_in_qdrant == stored_in_qdrant)
        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        articles = result.scalars().all()
        return articles
    
@app.post("/store_raw_articles")
async def store_raw_articles(articles: List[ArticleModel], session: AsyncSession = Depends(get_session)):
    async with session.begin():
        for article_data in articles:
            article = Article(**article_data.model_dump())
            session.add(article)
    return {"message": "Raw articles stored successfully."}

@app.post("/update_qdrant_flags")
async def update_qdrant_flags(urls: List[str], session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = update(Article).where(Article.url.in_(urls)).values(stored_in_qdrant=1)
            await session.execute(query)
        return {"message": "Qdrant flags updated successfully."}
    except Exception as e:
        logger.error(f"Error updating Qdrant flags: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/store_articles_with_embeddings")
async def store_processed_articles(articles: List[ProcessedArticleModel], session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            for article_data in articles:
                article = Article(**article_data.model_dump())
                session.add(article)
        return {"message": "Articles with embeddings stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))