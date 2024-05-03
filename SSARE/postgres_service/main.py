from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy import Column, Integer, String, Float
from sqlalchemy import select, insert, update
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import declarative_base, sessionmaker
from pydantic import BaseModel
from pydantic import ValidationError
import json
from contextlib import asynccontextmanager
import logging
from redis.asyncio import Redis
from core.utils import load_config
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import BaseModel

class ErrorResponseModel(BaseModel):
    detail: str

config = load_config()['postgresql']

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLAlchemy Base and Models
Base = declarative_base()

class Article(Base):
    __tablename__ = "articles"
    url = Column(String, primary_key=True)  # Url & Unique Identifier
    headline = Column(String)  # Headline
    paragraphs = Column(String)  # Text
    source = Column(String)  # 'cnn'
    embeddings = Column(ARRAY(Float))  # [3223, 2342, ..]
    entities = Column(JSONB)  # Change this line
    geocodes = Column(ARRAY(JSONB))  # JSON objects for geocodes
    embeddings_created = Column(Integer, default=0)  # Flag
    stored_in_qdrant = Column(Integer, default=0)  # Flag
    entities_extracted = Column(Integer, default=0)  # Flag
    geocoding_created = Column(Integer, default=0)  # Flag

class FullArticleModel(BaseModel):
    url: str
    headline: str
    paragraphs: str
    source: Optional[str]
    embeddings: Optional[List[float]]
    embeddings_created: int
    stored_in_qdrant: int
    entities: Optional[List[Dict[str, Any]]]  # Assuming entities are stored as a list of dictionaries
    entities_extracted: int
    geocodes: Optional[List[Dict[str, Any]]]  # Assuming geocodes are stored as a list of dictionaries
    geocoding_created: int

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
engine = create_async_engine(DATABASE_URL, echo=False)

AsyncSessionLocal = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# Redis connections
redis_conn_flags = Redis(host='redis', port=6379, db=0)  # For flags

# Database Dependency
from typing import AsyncGenerator
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        # Create tables here
        await conn.run_sync(Base.metadata.create_all)
    yield  # The application is now running
    # Cleanup logic here (if any)

app = FastAPI(lifespan=lifespan)


# Health Check Endpoint
@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}, 200

@app.get("/flags")
async def produce_flags():
    await redis_conn_flags.delete("scrape_sources")
    flags = ["cnn", "pynews", "bbc"]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@app.get("/articles", response_model=List[FullArticleModel])
async def get_articles_by_url_and_flags(
    url: Optional[str] = None,
    embeddings_created: Optional[int] = None,
    stored_in_qdrant: Optional[int] = None,
    entities_extracted: Optional[int] = None,
    geocoding_created: Optional[int] = None,
    skip: int = 0, 
    limit: int = 10, 
    session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        query = select(Article)
        if url is not None:
            query = query.filter(Article.url == url)
        if embeddings_created is not None:
            query = query.filter(Article.embeddings_created == embeddings_created)
        if stored_in_qdrant is not None:
            query = query.filter(Article.stored_in_qdrant == stored_in_qdrant)
        if entities_extracted is not None:
            query = query.filter(Article.entities_extracted == entities_extracted)
        if geocoding_created is not None:
            query = query.filter(Article.geocoding_created == geocoding_created)
        
        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        articles = result.scalars().all()
        
        # Convert articles to FullArticleModel
        articles_data = [
            FullArticleModel(
                url=article.url,
                headline=article.headline,
                paragraphs=article.paragraphs,
                source=article.source,
                embeddings=article.embeddings,
                embeddings_created=article.embeddings_created,
                stored_in_qdrant=article.stored_in_qdrant,
                entities=json.loads(article.entities) if article.entities else None,
                entities_extracted=article.entities_extracted,
                geocodes=[json.loads(geo) for geo in article.geocodes] if article.geocodes else None,
                geocoding_created=article.geocoding_created
            ) for article in articles
        ]
        
        return articles_data

from sqlalchemy import select, insert, update

@app.post("/store_raw_articles")
async def store_raw_articles(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=6379, db=1)
        logger.info("Connected to Redis")
        raw_articles = await redis_conn.lrange('raw_articles_queue', 0, -1)
        logger.info("Retrieved raw articles from Redis")

        async with session.begin():
            for raw_article in raw_articles:
                try:
                    article_data = json.loads(raw_article)
                    logger.info(f"Processing article: {article_data['url']}")

                    # Check if the article URL already exists in the database
                    existing_article = await session.execute(select(Article).where(Article.url == article_data['url']))
                    if existing_article.scalar_one_or_none() is not None:
                        # Update existing article
                        logger.info(f"Updating article: {article_data['url']}")
                        await session.execute(update(Article).where(Article.url == article_data['url']).values(**article_data))
                    else:
                        # Insert new article
                        logger.info(f"Inserting new article: {article_data['url']}")
                        await session.execute(insert(Article).values(**article_data))

                except ValidationError as e:
                    logger.error(f"Validation error for article: {e}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error: {e}")

        return {"message": "Raw articles processed successfully."}
    except Exception as e:
        logger.error(f"Error processing articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))



@app.post("/update_qdrant_flags")
async def update_qdrant_flags(data: Dict[str, List[str]], session: AsyncSession = Depends(get_session)):
    urls = data.get('urls', [])
    if not urls:
        logger.info("No URLs provided for updating Qdrant flags.")
        return {"message": "No URLs to update."}

    try:
        async with session.begin():
            query = update(Article).where(Article.url.in_(urls)).values(stored_in_qdrant=1)
            result = await session.execute(query)
            await session.commit()  # Explicit commit might be redundant but ensures transaction closure
            logger.info(f"Qdrant flags updated for URLs: {urls}, Rows affected: {result.rowcount}")
        return {"message": "Qdrant flags updated successfully."}
    except Exception as e:
        logger.error(f"Error updating Qdrant flags: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/store_articles_with_embeddings")
async def store_processed_articles(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=6379, db=6)  # Adjust the Redis DB index as needed
        articles_with_embeddings = await redis_conn.lrange('articles_with_embeddings', 0, -1)
        await redis_conn.delete('articles_with_embeddings')

        async with session.begin():
            for article_with_embedding in articles_with_embeddings:
                try:
                    article_data = json.loads(article_with_embedding)
                    logger.info(f"Storing article with embeddings: {article_data['url']}")

                    # Check if the article URL already exists in the database
                    existing_article = await session.execute(select(Article).where(Article.url == article_data['url']))
                    existing_article = existing_article.scalar_one_or_none()

                    if existing_article:
                        # Update existing article
                        logger.info(f"Updating article with embeddings: {article_data['url']}")
                        for key, value in article_data.items():
                            setattr(existing_article, key, value)
                    else:
                        # Create new article and add to session
                        article = Article(**article_data)
                        session.add(article)

                except ValidationError as e:
                    logger.error(f"Validation error for article: {e}")
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decoding error: {e}")

        return {"message": "Articles with embeddings stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing articles with embeddings: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/create_embedding_jobs")
async def create_embedding_jobs(session: AsyncSession = Depends(get_session)):
    """
    This function is triggered by an API. It reads from the PostgreSQL /articles table where embeddings_created = 0.
    It writes the articles without embeddings to the Redis queue 'articles_without_embedding_queue'.
    It doesn't trigger the generate_embeddings function in the NLP service. That is done by the scheduler.
    """
    logger.info("Trying to create embedding jobs.")
    try:
        async with session.begin():
            query = select(Article).where(Article.embeddings_created == 0)
            result = await session.execute(query)
            articles_without_embeddings = result.scalars().all()

        redis_conn_unprocessed_articles = await Redis(host='redis', port=6379, db=5)

        for article in articles_without_embeddings:
            article_dict = {
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs,
                'source': article.source,
                'embeddings': article.embeddings,
                'embeddings_created': article.embeddings_created,
                'stored_in_qdrant': article.stored_in_qdrant
            }
            await redis_conn_unprocessed_articles.lpush('articles_without_embedding_queue', json.dumps(article_dict))

        return {"message": "Embedding jobs created."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

async def push_articles_to_qdrant_upsert_queue(session):
    try:
        async with session.begin():
            query = select(Article).where(Article.stored_in_qdrant == 0)
            result = await session.execute(query)
            articles_to_push = result.scalars().all()

        redis_conn = await Redis(host='redis', port=6379, db=6)  # Adjust the Redis DB index as needed

        for article in articles_to_push:
            article_dict = {
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs,
                'source': article.source,
                'embeddings': article.embeddings,
                'embeddings_created': article.embeddings_created,
                'stored_in_qdrant': article.stored_in_qdrant
            }
            await redis_conn.lpush('articles_with_embeddings', json.dumps(article_dict))

        logger.info(f"Pushed {len(articles_to_push)} articles to Redis queue 'articles_with_embeddings'")
    except Exception as e:
        logger.error(f"Error pushing articles to Redis queue: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/trigger_qdrant_queue_push")
async def trigger_push_articles_to_queue(session: AsyncSession = Depends(get_session)):
    try:
        await push_articles_to_qdrant_upsert_queue(session)
        return {"message": "Articles pushed to queue successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# deducplication endpoint
@app.post("/deduplicate_articles")
async def deduplicate_articles(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Article).distinct(Article.url).group_by(Article.url).having(func.count() > 1)
            result = await session.execute(query)
            duplicate_articles = result.scalars().all()

        for article in duplicate_articles:
            logger.info(f"Duplicate article: {article.url}")
            await session.delete(article)

        return {"message": "Duplicate articles deleted successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create_entity_extraction_jobs")
async def create_entity_extraction_jobs(session: AsyncSession = Depends(get_session)):
    """
    This function reads from the PostgreSQL /articles table where entities_extracted = 0.
    It adds articles needing entity extraction to the Redis queue 'articles_without_entities_queue'.
    """
    logger.info("Starting to create entity extraction jobs.")
    try:
        async with session.begin():
            query = select(Article).where(Article.entities_extracted == 0).limit(3)
            result = await session.execute(query)
            articles_needing_entities = result.scalars().all()

        redis_conn = await Redis(host='redis', port=6379, db=2)  # Use a different Redis DB or adjust index as needed

        for article in articles_needing_entities:
            article_dict = {
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs
            }
            await redis_conn.lpush('articles_without_entities_queue', json.dumps(article_dict))

        logger.info(f"Entity extraction jobs for {len(articles_needing_entities)} articles created.")
        return {"message": "Entity extraction jobs created successfully."}
    except Exception as e:
        logger.error(f"Error creating entity extraction jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create_geocoding_jobs")
async def create_geocoding_jobs(session: AsyncSession = Depends(get_session)):
    """
    This function reads from the PostgreSQL /articles table where geocoding_created = 0.
    It adds articles needing geocoding to the Redis queue 'articles_without_geocoding_queue',
    including their extracted entities that might contain location names.
    """
    logger.info("Starting to create geocoding jobs.")
    try:
        async with session.begin():
            query = select(Article).where(Article.geocoding_created == 0)
            result = await session.execute(query)
            articles_needing_geocoding = result.scalars().all()

        redis_conn = await Redis(host='redis', port=6379, db=3)  # Use a different Redis DB or adjust index as needed

        for article in articles_needing_geocoding:
             article_dict = {
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs,
                'entities': json.dumps(article.entities)  # Ensure entities are serialized if they are not already a string
            }
        await redis_conn.lpush('articles_without_geocoding_queue', json.dumps(article_dict))

        logger.info(f"Geocoding jobs for {len(articles_needing_geocoding)} articles created, including entities data.")
        return {"message": "Geocoding jobs created successfully, including entities."}
    except Exception as e:
        logger.error(f"Error creating geocoding jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

