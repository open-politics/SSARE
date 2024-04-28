from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer
from core.models import ArticleBase
import json
import logging
from core.utils import load_config
from redis.asyncio import Redis
import asyncio
from prefect import task, flow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = load_config()['nlp']
app = FastAPI()
token = config['HUGGINGFACE_TOKEN']
model = SentenceTransformer("jinaai/jina-embeddings-v2-base-en", use_auth_token=token)

@app.get("/healthz")
async def healthcheck():
    return {"message": "NLP Service Running"}, 200

async def retrieve_articles_from_redis(redis_conn_raw, batch_size=1000):
    raw_articles_json = []
    while True:
        batch = await redis_conn_raw.lrange('articles_without_embedding_queue', 0, batch_size - 1)
        if not batch:
            break
        raw_articles_json.extend(batch)
        await redis_conn_raw.ltrim('articles_without_embedding_queue', batch_size, -1)
    logger.info(f"Retrieved {len(raw_articles_json)} articles from Redis")
    return raw_articles_json

async def process_article(raw_article_json):
    raw_article = json.loads(raw_article_json.decode('utf-8'))
    article = ArticleBase(**raw_article)

    embeddings = model.encode(article.headline + " ".join(article.paragraphs[:5])).tolist()

    article_with_embeddings = {
        "headline": article.headline,
        "paragraphs": article.paragraphs,
        "embeddings": embeddings,
        "embeddings_created": 1,
        "url": article.url,
        "source": article.source,
        "stored_in_qdrant": 0
    }

    logger.info(f"Generated embeddings for article: {article.url}, Embeddings Length: {len(embeddings)}")
    return article_with_embeddings

async def write_articles_to_redis(redis_conn_processed, articles_with_embeddings):
    serialized_articles = [json.dumps(article) for article in articles_with_embeddings]
    await redis_conn_processed.lpush('articles_with_embeddings', *serialized_articles)
    logger.info(f"Wrote {len(articles_with_embeddings)} articles with embeddings to Redis")

async def generate_embeddings_flow(redis_conn_raw, redis_conn_processed, batch_size=1000):
    logger.info("Starting embeddings generation process")
    
    try:
        raw_articles_json = await retrieve_articles_from_redis(redis_conn_raw, batch_size)
        articles_with_embeddings = await asyncio.gather(*[process_article(raw_article_json) for raw_article_json in raw_articles_json])
        await write_articles_to_redis(redis_conn_processed, articles_with_embeddings)
        
        logger.info("Embeddings generation process completed")
    except Exception as e:
        logger.exception(f"Error in generate_embeddings_flow: {e}")
        raise e

@app.post("/generate_embeddings")
async def generate_embeddings(batch_size: int = 1000):
    try:
        async with Redis(host='redis', port=6379, db=5) as redis_conn_raw, \
                   Redis(host='redis', port=6379, db=6) as redis_conn_processed:
            try:
                await generate_embeddings_flow(redis_conn_raw, redis_conn_processed, batch_size)
                return {"message": "Embeddings generated successfully"}
            except Exception as e:
                logger.exception(f"Error generating embeddings: {e}")
                raise HTTPException(status_code=500, detail="Error generating embeddings")
    except Exception as e:
        logger.exception(f"Error connecting to Redis: {e}")
        raise HTTPException(status_code=500, detail="Error connecting to Redis")

@app.get("/generate_query_embeddings")
async def generate_query_embedding(query: str):
    try:
        embeddings = model.encode(query).tolist()
        logger.info(f"Generated embeddings for query: {query}, Embedding Length: {len(embeddings)}")
        return {"message": "Embeddings generated", "embeddings": embeddings}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
