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
from sqlalchemy import text
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy import bindparam
from sqlalchemy import cast
from sqlalchemy import or_
from sqlalchemy.dialects.postgresql import JSONB

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
    entities = Column(JSONB)  # JSONB for storing entities
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

AsyncSessionLocal = sessionmaker(bind=engine,
 class_=AsyncSession, expire_on_commit=False)

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


app = FastAPI(lifespan=lifespan)


# Health Check Endpoint
@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}, 200

@app.get("/flags")
async def produce_flags():
    await redis_conn_flags.delete("scrape_sources")
    flags = ["cnn", "bbc", "dw"]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@app.get("/articles", response_model=List[FullArticleModel])
async def get_articles(
    url: Optional[str] = None,
    embeddings_created: Optional[int] = None,
    stored_in_qdrant: Optional[int] = None,
    entities_extracted: Optional[int] = None,
    geocoding_created: Optional[int] = None,
    has_gpe: bool = False,  # New parameter to filter for GPE entities
    search_text: Optional[str] = None,  # New parameter for text search
    skip: int = 0, 
    limit: int = 10, 
    session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        query = select(Article)
        if url:
            query = query.filter(Article.url == url)
        if embeddings_created is not None:
            query = query.filter(Article.embeddings_created == embeddings_created)
        if stored_in_qdrant is not None:
            query = query.filter(Article.stored_in_qdrant == stored_in_qdrant)
        if entities_extracted is not None:
            query = query.filter(Article.entities_extracted == entities_extracted)
        if geocoding_created is not None:
            query = query.filter(Article.geocoding_created == geocoding_created)
        if has_gpe:
            query = query.filter(Article.entities.op('@>')(cast('[{"entity_type":"GPE"}]', JSONB)))
        if search_text:
            # Search in headline or paragraphs
            query = query.filter(
                or_(
                    Article.headline.ilike(f'%{search_text}%'), 
                    Article.paragraphs.ilike(f'%{search_text}%')
                )
            )
        
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
            query = update(Article).where(Article.url.in_(urls)).values(stored_in_qdrant=1).where(Article.embeddings.isnot(None))
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
                            if key == 'embeddings':
                                setattr(existing_article, 'embeddings_created', 1 if value else 0)
                            setattr(existing_article, key, value)
                    else:
                        # Create new article and add to session
                        article_data['embeddings_created'] = 1 if 'embeddings' in article_data else 0
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
    logger.info("Trying to create embedding jobs.")
    try:
        async with session.begin():
            # Select articles where embeddings are not created yet and embeddings are not None
            query = select(Article).where(or_(Article.embeddings_created == 0, Article.embeddings.isnot(None)))
            result = await session.execute(query)
            articles_without_embeddings = result.scalars().all()

        redis_conn_unprocessed_articles = await Redis(host='redis', port=6379, db=5)
        articles_list = [
            json.dumps({
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs
            }) for article in articles_without_embeddings
        ]

        if articles_list:
            # Using RPUSH for better practice in Redis (list will maintain the order of insertion)
            await redis_conn_unprocessed_articles.rpush('articles_without_embedding_queue', *articles_list)

        return {"message": f"Embedding jobs created for {len(articles_list)} articles."}
    except Exception as e:
        logger.error("Failed to create embedding jobs: ", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

async def push_articles_to_qdrant_upsert_queue(session):
    ## Pushing articles that have embeddings and are not yet stored in qdrant to the queue
    try:
        async with session.begin():
            query = select(Article).where(Article.stored_in_qdrant == 0).where(Article.embeddings.isnot(None))
            result = await session.execute(query)
            articles_to_push = result.scalars().all()
            logger.info(f"Articles to push: {articles_to_push}")

        redis_conn = await Redis(host='redis', port=6379, db=6)
        articles_list = [json.dumps({'url': article.url, 'embeddings': article.embeddings, 'headline':article.headline, 'paragraphs': article.paragraphs, 'source':article.source}) for article in articles_to_push]
        logger.info(articles_list)
        if articles_list:
            await redis_conn.lpush('articles_with_embeddings', *articles_list)
            logger.info(f"Pushed {len(articles_list)} articles to Redis queue 'articles_with_embeddings'")
    except Exception as e:
        logger.error("Error pushing articles to Redis queue: ", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    
@app.post("/trigger_qdrant_queue_push")
async def trigger_push_articles_to_queue(session: AsyncSession = Depends(get_session)):
    ## This is an endpoint intended to async trigger the push_articles_to_qdrant_upsert_queue function
    ## So the HTTP request can be just dropped off, checks out and the function will be executed in the background
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
            query = select(Article).where(Article.entities_extracted == 0).limit(50)
            result = await session.execute(query)
            articles_needing_entities = result.scalars().all()

        redis_conn = await Redis(host='redis', port=6379, db=2)  # Use a different Redis DB or adjust index as needed

        for article in articles_needing_entities:
            article_dict = {
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs
            }
            await redis_conn.lpush('articles_without_entities_queue', json.dumps(article_dict, ensure_ascii=False))

        logger.info(f"Entity extraction jobs for {len(articles_needing_entities)} articles created.")
        return {"message": "Entity extraction jobs created successfully."}
    except Exception as e:
        logger.error(f"Error creating entity extraction jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/create_geocoding_jobs")
async def create_geocoding_jobs(session: AsyncSession = Depends(get_session)):
    """
    This function reads from the PostgreSQL /articles table where geocoding_created = 0
    and entities_extracted = 1. It adds articles that need geocoding and contain at least one
    GPE entity to the Redis queue 'articles_without_geocoding_queue'.
    """
    logger.info("Starting to create geocoding jobs.")
    try:
        async with session.begin():
            # Ensure the JSON is cast to jsonb for PostgreSQL to understand it
            jsonb_filter = bindparam('jsonb_filter', value='[{"entity_type":"GPE"}]', type_=JSONB)
            query = select(Article).where(
                Article.embeddings_created == 1,
                Article.entities_extracted == 1,
                Article.geocoding_created == 1,
                Article.entities.op('@>')(jsonb_filter)
            )
        # Execute the query with the correct jsonb parameter
            result = await session.execute(query)
            articles_needing_geocoding = result.scalars().all()

        # Proceed to push these filtered articles to Redis
        redis_conn = await Redis(host='redis', port=6379, db=3)
        for article in articles_needing_geocoding:
            article_dict = {
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs,
                'entities': json.dumps(article.entities, ensure_ascii=False)
            }
            await redis_conn.lpush('articles_without_geocoding_queue', json.dumps(article_dict, ensure_ascii=False))

        logger.info(f"Geocoding jobs for {len(articles_needing_geocoding)} articles created, including entities data.")
        return {"message": "Geocoding jobs created successfully, including entities."}
    except Exception as e:
        logger.error(f"Error creating geocoding jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
