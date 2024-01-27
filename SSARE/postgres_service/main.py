from pydantic import BaseModel, ValidationError
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query, Request
import json
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from contextlib import contextmanager
from redis.asyncio import Redis 
import logging
from core.utils import load_config

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Pydantic models
class ArticleModel(BaseModel):
    url: str
    headline: str
    paragraphs: str  # JSON string
    source: Optional[str]
    embedding: Optional[str]  # JSON string
    embeddings_created: int = 0  # 0 = False, 1 = True
    isStored_in_qdrant: int = 0  # 0 = False, 1 = True

class ProcessedArticleModel(ArticleModel):
    pass

# Initialize the connection pool
def init_db_pool():
    config = load_config()['postgresql']
    return SimpleConnectionPool(minconn=1, maxconn=10,
                                dbname=config["postgres_db"],
                                user=config["postgres_user"],
                                password=config["postgres_password"],
                                host=config["postgres_host"])

pool = init_db_pool()

@contextmanager
def get_db_connection():
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)

# FastAPI app initialization
app = FastAPI()

# Redis connections
redis_conn_flags = Redis(host='redis', port=6379, db=0)  # For flags
redis_conn_articles = Redis(host='redis', port=6379, db=2)  # For articles

@app.get("/flags")
async def produce_flags():
    await redis_conn_flags.delete("scrape_sources")
    flags = ["cnn"]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@app.get('/articles', response_model=List[ArticleModel])
async def get_articles(embeddings_created: Optional[bool] = Query(None), isStored_in_Qdrant: Optional[bool] = Query(None), skip: int = 0, limit: int = 10):
    with get_db_connection() as conn:
        cur = conn.cursor()
        query = "SELECT * FROM articles"
        conditions = []
        if embeddings_created is not None:
            conditions.append(f"embeddings_created = {embeddings_created}")
        if isStored_in_Qdrant is not None:
            conditions.append(f"isStored_in_qdrant = {isStored_in_Qdrant}")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += f" OFFSET {skip} LIMIT {limit}"

        cur.execute(query)
        articles = cur.fetchall()
        cur.close()
        return articles

@app.post("/store_raw_articles")
async def store_raw_articles():
    try:
        redis_conn = await Redis(host='redis', port=6379, db=1)
        logger.info("Connected to Redis")
        raw_articles = await redis_conn.lrange('raw_articles_queue', 0, -1)
        logger.info("Retrieved raw articles from Redis")
        
        with get_db_connection() as conn:
            cur = conn.cursor()
            batch_size = 50
            for i in range(0, len(raw_articles), batch_size):
                batch = raw_articles[i:i + batch_size]
                for raw_article in batch:
                    try:
                        article_data = json.loads(raw_article)
                        article = ArticleModel(**article_data)
                        insert_query = "INSERT INTO articles (url, headline, paragraphs, source, embedding, embeddings_created, isStored_in_qdrant) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                        cur.execute(insert_query, (article.url, article.headline, article.paragraphs, article.source, article.embedding, article.embeddings_created, article.isStored_in_qdrant))
                    except ValidationError as e:
                        logger.error(f"Validation error for article: {e}")
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decoding error: {e}")
                conn.commit()
            cur.close()
        return {"message": "Raw articles stored successfully."}
    except Exception as e:
        logger.error(f"Error storing articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))