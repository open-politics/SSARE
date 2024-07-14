import os
import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from sqlmodel import SQLModel, Field, create_engine, Session, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from pydantic import BaseModel, ValidationError
from contextlib import asynccontextmanager
from redis.asyncio import Redis
from fastapi.responses import StreamingResponse
from core.service_mapping import config

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SQLModel Base and Models
class Article(SQLModel, table=True):
    __tablename__ = "articles"
    url: str = Field(primary_key=True)
    headline: str
    paragraphs: str
    source: Optional[str]
    embeddings: Optional[List[float]]
    entities: Optional[Dict[str, Any]]
    geocodes: Optional[List[Dict[str, Any]]]
    embeddings_created: int = 0
    stored_in_qdrant: int = 0
    entities_extracted: int = 0
    geocoding_created: int = 0

class FullArticleModel(BaseModel):
    url: str
    headline: str
    paragraphs: str
    source: Optional[str]
    embeddings: Optional[List[float]]
    embeddings_created: int
    stored_in_qdrant: int
    entities: Optional[List[Dict[str, Any]]]
    entities_extracted: int
    geocodes: Optional[List[Dict[str, Any]]]
    geocoding_created: int

class ArticleModel(BaseModel):
    url: str
    headline: str
    paragraphs: str
    source: Optional[str]
    embeddings: Optional[List[float]]
    embeddings_created: int = 0
    stored_in_qdrant: int = 0

DATABASE_URL = (
    f"postgresql+asyncpg://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
    f"@postgres:{config.ARTICLES_DB_PORT}/{config.ARTICLES_DB_NAME}"
)
engine = create_async_engine(DATABASE_URL, echo=False)
session_local = AsyncSession(engine, expire_on_commit=False)

# Redis connection
redis_conn_flags = Redis(host='redis', port=config.REDIS_PORT, db=0)  # For flags

# Dependency
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_local() as session:
        yield session

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield

app = FastAPI(lifespan=lifespan)

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
    has_gpe: bool = False,
    search_text: Optional[str] = None,
    skip: int = 0, 
    limit: int = 10, 
    session: AsyncSession = Depends(get_session)
):
    async with session.begin():
        query = select(Article)
        if url:
            query = query.where(Article.url == url)
        if embeddings_created is not None:
            query = query.where(Article.embeddings_created == embeddings_created)
        if stored_in_qdrant is not None:
            query = query.where(Article.stored_in_qdrant == stored_in_qdrant)
        if entities_extracted is not None:
            query = query.where(Article.entities_extracted == entities_extracted)
        if geocoding_created is not None:
            query = query.where(Article.geocoding_created == geocoding_created)
        if search_text:
            query = query.where(
                or_(
                    Article.headline.ilike(f'%{search_text}%'), 
                    Article.paragraphs.ilike(f'%{search_text}%')
                )
            )
        
        query = query.offset(skip).limit(limit)
        result = await session.execute(query)
        articles = result.scalars().all()
        articles_data = [
            FullArticleModel(
                url=article.url,
                headline=article.headline,
                paragraphs=article.paragraphs,
                source=article.source,
                embeddings=article.embeddings,
                embeddings_created=article.embeddings_created,
                stored_in_qdrant=article.stored_in_qdrant,
                entities=article.entities,
                entities_extracted=article.entities_extracted,
                geocodes=article.geocodes,
                geocoding_created=article.geocoding_created
            ) for article in articles
        ]
        return articles_data

@app.post("/store_raw_articles")
async def store_raw_articles(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=1)
        logger.info("Connected to Redis")
        raw_articles = await redis_conn.lrange('raw_articles_queue', 0, -1)
        logger.info("Retrieved raw articles from Redis")

        async with session.begin():
            for raw_article in raw_articles:
                try:
                    article_data = json.loads(raw_article)
                    logger.info(f"Processing article: {article_data['url']}")

                    existing_article = await session.execute(select(Article).where(Article.url == article_data['url']))
                    if existing_article.scalar_one_or_none() is not None:
                        logger.info(f"Updating article: {article_data['url']}")
                        await session.execute(update(Article).where(Article.url == article_data['url']).values(**article_data))
                    else:
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
            await session.commit()
            logger.info(f"Qdrant flags updated for URLs: {urls}, Rows affected: {result.rowcount}")
        return {"message": "Qdrant flags updated successfully."}
    except Exception as e:
        logger.error(f"Error updating Qdrant flags: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/store_articles_with_embeddings")
async def store_processed_articles(session: AsyncSession = Depends(get_session)):
    try:
        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=6)
        articles_with_embeddings = await redis_conn.lrange('articles_with_embeddings', 0, -1)
        await redis_conn.delete('articles_with_embeddings')

        async with session.begin():
            for article_with_embedding in articles_with_embeddings:
                try:
                    article_data = json.loads(article_with_embedding)
                    logger.info(f"Storing article with embeddings: {article_data['url']}")

                    existing_article = await session.execute(select(Article).where(Article.url == article_data['url']))
                    existing_article = existing_article.scalar_one_or_none()

                    if existing_article:
                        logger.info(f"Updating article with embeddings: {article_data['url']}")
                        for key, value in article_data.items():
                            if key == 'embeddings':
                                setattr(existing_article, 'embeddings_created', 1 if value else 0)
                            setattr(existing_article, key, value)
                    else:
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
            query = select(Article).where(or_(Article.embeddings_created == 0, Article.embeddings.isnot(None)))
            result = await session.execute(query)
            articles_without_embeddings = result.scalars().all()

        redis_conn_unprocessed_articles = await Redis(host='redis', port=config.REDIS_PORT, db=5)
        articles_list = [
            json.dumps({
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs
            }) for article in articles_without_embeddings
        ]

        if articles_list:
            await redis_conn_unprocessed_articles.rpush('articles_without_embedding_queue', *articles_list)

        return {"message": f"Embedding jobs created for {len(articles_list)} articles."}
    except Exception as e:
        logger.error("Failed to create embedding jobs: ", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

async def push_articles_to_qdrant_upsert_queue(session):
    try:
        async with session.begin():
            query = select(Article).where(Article.stored_in_qdrant == 0).where(Article.embeddings.isnot(None))
            result = await session.execute(query)
            articles_to_push = result.scalars().all()
            logger.info(f"Articles to push: {articles_to_push}")

        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=6)
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
    try:
        await push_articles_to_qdrant_upsert_queue(session)
        return {"message": "Articles pushed to queue successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    logger.info("Starting to create entity extraction jobs.")
    try:
        async with session.begin():
            query = select(Article).where(Article.entities_extracted == 0)
            result = await session.execute(query)
            articles_needing_entities = result.scalars().all()

        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=2)

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
    logger.info("Starting to create geocoding jobs.")
    try:
        async with session.begin():
            query = select(Article).where(
                Article.entities_extracted == 1,
                Article.geocoding_created == 0
            )
            result = await session.execute(query)
            articles_needing_geocoding = result.scalars().all()

        redis_conn = await Redis(host='redis', port=config.REDIS_PORT, db=3)
        for article in articles_needing_geocoding:
            article_data = json.dumps({
                'url': article.url,
                'headline': article.headline,
                'paragraphs': article.paragraphs,
                'entities': article.entities
            }, ensure_ascii=False)
            await redis_conn.lpush('articles_without_geocoding_queue', article_data)

        logger.info(f"Pushed {len(articles_needing_geocoding)} articles to geocoding queue.")
        return {"message": "Geocoding jobs created successfully."}
    except Exception as e:
        logger.error(f"Error creating geocoding jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cleanup_flags")
async def cleanup_flags(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            embeddings_fix_query = (
                update(Article)
                .where(Article.embeddings_created == 1, Article.embeddings == None)
                .values(embeddings_created=0)
            )
            embeddings_fix_result = await session.execute(embeddings_fix_query)
            logger.info(f"Fixed embeddings_created flags for {embeddings_fix_result.rowcount} articles.")

            qdrant_fix_query = (
                update(Article)
                .where(Article.stored_in_qdrant == 1, Article.embeddings == None)
                .values(stored_in_qdrant=0)
            )
            qdrant_fix_result = await session.execute(qdrant_fix_query)
            logger.info(f"Fixed stored_in_qdrant flags for {qdrant_fix_result.rowcount} articles.")

            entities_fix_query = (
                update(Article)
                .where(Article.entities_extracted == 1, Article.entities == None)
                .values(entities_extracted=0)
            )
            entities_fix_result = await session.execute(entities_fix_query)
            logger.info(f"Fixed entities_extracted flags for {entities_fix_result.rowcount} articles.")

            geocoding_fix_query = (
                update(Article)
                .where(Article.geocoding_created == 1, Article.geocodes == None)
                .values(geocoding_created=0)
            )
            geocoding_fix_result = await session.execute(geocoding_fix_query)
            logger.info(f"Fixed geocoding_created flags for {geocoding_fix_result.rowcount} articles.")

            await session.commit()

        return {"message": "Flag cleanup completed successfully."}
    except Exception as e:
        logger.error(f"Error during flag cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))
