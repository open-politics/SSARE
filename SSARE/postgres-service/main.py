import logging
from fastapi import FastAPI
from core.adb import create_db_and_tables, get_session
from core.middleware import add_cors_middleware
from routes.main import api_router

import logfire

logfire.configure()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def lifespan(app):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=lifespan)
add_cors_middleware(app)

app.include_router(api_router)

@app.get("/healthz")
async def healthcheck():
    return {"message": "OK"}, 200



## All routes are in their respective folders, please check what kind of functionality you are looking for in there