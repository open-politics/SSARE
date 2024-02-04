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
    embeddings: Optional[List[float]] 
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

def create_articles_table():
    with get_db_connection() as conn:
        cur = conn.cursor()
        create_table_query = """
        CREATE TABLE IF NOT EXISTS articles (
            url TEXT PRIMARY KEY,
            headline TEXT,
            paragraphs TEXT,  -- JSON string
            source TEXT,
            embeddings INT[],  --- array of ints
            embeddings_created INT DEFAULT 0,
            isStored_in_qdrant INT DEFAULT 0
        )
        """
        cur.execute(create_table_query)
        conn.commit()
        cur.close()

create_articles_table()

def create_processed_articles_table():
    with get_db_connection() as conn:
        cur = conn.cursor()
        create_table_query = """
        CREATE TABLE IF NOT EXISTS processed_articles (
            url TEXT PRIMARY KEY,
            headline TEXT,
            paragraphs TEXT,  -- JSON string
            source TEXT,
            embeddings INT[],  --- array of ints
            embeddings_created INT DEFAULT 1,
            isStored_in_qdrant INT DEFAULT 0
        )
        """
        cur.execute(create_table_query)
        conn.commit()
        cur.close()

create_processed_articles_table()

# Redis connections
redis_conn_flags = Redis(host='redis', port=6379, db=0)  # For flags


@app.get("/flags")
async def produce_flags():
    await redis_conn_flags.delete("scrape_sources")
    flags = ["cnn"]
    for flag in flags:
        await redis_conn_flags.lpush("scrape_sources", flag)
    return {"message": f"Flags produced: {', '.join(flags)}"}

@app.get('/articles', response_model=List[ArticleModel])
async def get_articles(embeddings_created: Optional[int] = Query(None), isStored_in_Qdrant: Optional[int] = Query(None), skip: int = 0, limit: int = 10):
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
        rows = cur.fetchall()
        cur.close()

        # Convert the articles to a list of ArticleModel objects
        articles = [dict(zip([column[0] for column in cur.description], row)) for row in rows]
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
                        print(raw_article)
                        article_data = json.loads(raw_article)
                        logger.info(f"Storing article: {article_data['url']}")
                        logger.info(f"Article data: {article_data}['paragraphs'][:100]")
                        article = ArticleModel(**article_data)
                        
                        # Check if the article URL already exists in the database
                        cur.execute("SELECT 1 FROM articles WHERE url = %s", (article.url,))
                        if cur.fetchone() is not None:
                            logger.info(f"Article already exists: {article.url}")
                            continue

                        insert_query = "INSERT INTO articles (url, headline, paragraphs, source, embeddings, embeddings_created, isStored_in_qdrant) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                        embeddings_json = json.dumps(article.embeddings)  # Convert the list of floats to a JSON string
                        cur.execute(insert_query, (article.url, article.headline, article.paragraphs, article.source, embeddings_json, article.embeddings_created, article.isStored_in_qdrant))
                    except ValidationError as e:
                        logger.error(f"Validation error for article: {e}")
                        logger.error(f"Article data: {article_data}")
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decoding error: {e}")
                conn.commit()
            cur.close()
        return {"message": "Raw articles stored successfully."}
    except Exception as e:
        logger.error(f"Error storing articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/store_articles_with_embeddings")
async def store_processed_articles():
    try:
        redis_conn = await Redis(host='redis', port=6379, db=6)
        articles_with_embeddings = await redis_conn.lrange('articles_with_embeddings', 0, -1)
        await redis_conn.delete('articles_with_embeddings')

        with get_db_connection() as conn:
            cur = conn.cursor()
            batch_size = 10  # Adjust the batch size as needed
            for i in range(0, len(articles_with_embeddings), batch_size):
                batch = articles_with_embeddings[i:i + batch_size]
                for article_with_embedding in batch:
                    try:
                        article_data = json.loads(article_with_embedding)
                        article = ProcessedArticleModel(**article_data)
                        insert_query = "INSERT INTO processed_articles (url, headline, paragraphs, source, embeddings, embeddings_created, isStored_in_qdrant) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                        cur.execute(insert_query, (article.url, article.headline, article.paragraphs, article.source, article.embeddings, article.embeddings_created, article.isStored_in_qdrant))
                    except ValidationError as e:
                        logger.error(f"Validation error for article: {e}")
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decoding error: {e}")
                conn.commit()
            cur.close()
        return {"message": "Articles with embeddings stored successfully in PostgreSQL."}
    except Exception as e:
        logger.error(f"Error storing articles: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/update_qdrant_flags")
async def update_qdrant_flags(urls: List[str]):
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            update_query = "UPDATE processed_articles SET isStored_in_qdrant = 1 WHERE url = %s"
            for url in urls:
                cur.execute(update_query, (url,))
            conn.commit()
            cur.close()
        return {"message": "Qdrant flags updated successfully."}
    except Exception as e:
        logger.error(f"Error updating Qdrant flags: {e}")
        raise HTTPException(status_code=400, detail=str(e))


