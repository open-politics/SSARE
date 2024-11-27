import json
import logging
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from core.service_mapping import ServiceConfig
from core.utils import logger
from prefect.deployments import run_deployment

async def lifespan(app):
    yield

app = FastAPI(lifespan=lifespan)
config = ServiceConfig()

logger.error("Initializing Ray for Entity Service")

class EntityRequest(BaseModel):
    batch_size: int = 50

@app.get("/healthz")
async def healthcheck():
    return {"message": "Entity Service Running"}, 200

@app.post("/extract_entities")
async def extract_entities(request: EntityRequest):
    try:
        logger.info(f"Initiating entity extraction with batch size: {request.batch_size}")
        await run_deployment(
            name="extract-entities-deployment",
            parameters={"batch_size": request.batch_size}
        )
        return {"message": "Entity extraction process initiated successfully"}
    except Exception as e:
        logger.error(f"Error initiating entity extraction: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))