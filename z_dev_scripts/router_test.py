from fastapi import FastAPI, HTTPException
from redis.asyncio import Redis
from contextlib import asynccontextmanager
import logging
from prefect import task, flow
from core.models import Article, Articles
from core.db import engine, get_session
import json
import asyncio
from script_scraper import scrape_sources_flow
from semantic_router import Route, RouteLayer
from semantic_router.encoders import OpenAIEncoder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define routes for semantic router
politics = Route(
    name="politics",
    utterances=[
        "The recent Senate hearing on foreign policy has sparked intense debate among lawmakers. Critics argue that the proposed measures could strain international relations, while supporters claim they are necessary for national security. The hearing, which lasted over six hours, saw heated exchanges between senators from both parties.",
        "In a surprising turn of events, the city council voted unanimously to approve a controversial zoning change. The decision, which will allow for the construction of a new high-rise development in the historic downtown area, has been met with mixed reactions from residents. Proponents argue that it will bring much-needed economic growth,",
        "The President's latest executive order on climate change has drawn both praise and criticism from various sectors. Environmental groups hail it as a significant step towards reducing carbon emissions, while industry leaders express concerns about potential job losses. The order, which sets ambitious targets for renewable energy adoption,",
        "A new poll released today shows a significant shift in public opinion regarding healthcare reform. The survey, conducted by a nonpartisan research group, indicates that a majority of Americans now support a universal healthcare system. This marks a notable change from previous years and could have major implications for upcoming policy debates.",
        "The state legislature is set to vote on a comprehensive education bill next week. The proposed legislation aims to address longstanding issues in the public school system, including teacher pay, classroom sizes, and standardized testing. Educators and parents' groups have been lobbying intensively, with both sides making their case to lawmakers.",
    ],
)

chitchat = Route(
    name="chitchat",
    utterances=[
        "how's the weather today?",
        "how are things going?",
        "lovely weather today",
        "the weather is horrendous",
        "let's go to the chippy",
    ],
)

routes = [politics, chitchat]

# Initialize encoder and route layer
os.environ["OPENAI_API_KEY"] = "<YOUR_API_KEY>"
encoder = OpenAIEncoder()
route_layer = RouteLayer(encoder=encoder, routes=routes)

@task
async def setup_redis_connection():
    return Redis(host='redis', port=6379, db=1, decode_responses=True)

@task
async def close_redis_connection(redis_conn):
    try:
        await redis_conn.aclose()
    except RuntimeError as e:
        logger.warning(f"Error closing Redis connection: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_conn = Redis(host='redis', port=6379, db=1, decode_responses=True)
    app.state.redis = redis_conn
    yield
    await redis_conn.aclose()

app = FastAPI(lifespan=lifespan)

@task
async def get_scraper_config():
    with open("scrapers/scrapers_config.json") as f:
        return json.load(f)

@task
async def get_flags():
    redis_conn_flags = Redis(host='redis', port=6379, db=0, decode_responses=True)
    flags = await redis_conn_flags.lrange('scrape_sources', 0, -1)
    await redis_conn_flags.aclose()
    return flags

@task
async def wait_for_scraping_completion(redis_conn):
    while await redis_conn.get('scraping_in_progress') == '1':
        await asyncio.sleep(0.5)

@flow
async def scrape_data():
    redis_conn = await setup_redis_connection()
    try:
        flags = await get_flags()
        logger.info(f"Creating scrape jobs for {flags}")

        await scrape_sources_flow(flags)

        await wait_for_scraping_completion(redis_conn)
    except Exception as e:
        logger.error(f"Error in scrape_data flow: {str(e)}")
    finally:
        await close_redis_connection(redis_conn)
    logger.info(f"Scrape data task completed.")
    return {"status": "ok"}

@app.post("/create_scrape_jobs")
async def create_scrape_jobs():
    return await scrape_data()

@app.get("/healthz")
def healthz_check():
    return {"status": "ok"}

@app.post("/classify_article")
async def classify_article(article: Article):
    try:
        classification = route_layer(article.headline).name
        return {"classification": classification}
    except Exception as e:
        logger.error(f"Error classifying article: {str(e)}")
        raise HTTPException(status_code=500, detail="Error classifying article")