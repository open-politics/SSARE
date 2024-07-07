from typing import List
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from core.utils import load_config 
from core.models import ArticleBase, ArticlePydantic
import tempfile
import os
from fastapi import APIRouter
from pydantic import BaseModel
import httpx
import json
import logging
from fastapi.responses import StreamingResponse

app = FastAPI()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config = load_config()['postgresql']

# Database setup
DATABASE_URL = f"postgresql+asyncpg://{config['postgres_user']}:{config['postgres_password']}@{config['postgres_host']}/{config['postgres_db']}"
engine = create_async_engine(DATABASE_URL)
if os.getenv("INITDB") == "True":
    logger.info("Initializing database")
    SQLModel.metadata.create_all(engine)

# Dependency to get DB session
async def get_db():
    async with AsyncSession(engine) as session:
        yield session

@app.get("/healthz")
async def healthcheck():
    logger.info("Health check requested")
    return {"message": "RAG Service Running"}, 200

@app.get("/articles/", response_model=List[ArticlePydantic])
async def read_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    logger.info(f"Fetching articles with skip={skip} and limit={limit}")
    statement = select(ArticleBase).offset(skip).limit(limit)
    result = await db.execute(statement)
    db_articles = result.scalars().all()
    return db_articles

async def get_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    logger.info(f"Getting articles with skip={skip} and limit={limit}")
    statement = select(ArticleBase).offset(skip).limit(limit)
    result = await db.execute(statement)
    db_articles = result.scalars().all()
    return db_articles

class R2RDocument(BaseModel):
    type: str
    data: str
    metadata: dict

class R2RIngestDocumentsRequest(BaseModel):
    documents: List[R2RDocument]

@app.post("/ingest_documents")
async def ingest_documents(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    logger.info("Starting document ingestion")
    # Fetch articles from PostgreSQL
    articles = await get_articles(limit=100, db=db)  # Adjust the limit as needed

    # Create a temporary directory to store files
    with tempfile.TemporaryDirectory() as temp_dir:
        files = []
        metadatas = []

        for i, article in enumerate(articles):
            # Create a temporary file for each article
            file_path = os.path.join(temp_dir, f"article_{i}.txt")
            with open(file_path, "w") as f:
                f.write("\n".join(article.paragraphs))
            files.append(("files", (f"article_{i}.txt", open(file_path, "rb"), "text/plain")))

            # Prepare metadata for each article
            metadata = {
                "title": article.headline,
                "url": article.url,
                "published_by": str(article.source),
                "entities": article.entities
            }
            metadatas.append(metadata)

        # Function to send request to R2R service
        async def send_to_r2r():
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post(
                        "http://r2r:8000/v1/ingest_files",
                        files=files,
                        data={"metadatas": json.dumps(metadatas)},
                        timeout=30.0  # Adjust timeout as needed
                    )
                    response.raise_for_status()
                    logger.info(f"Successfully ingested {len(articles)} documents to R2R")
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error occurred during ingestion: {e}")
                except httpx.RequestError as e:
                    logger.error(f"An error occurred while requesting ingestion: {e}")

        # Add the task to send files to R2R in the background
        background_tasks.add_task(send_to_r2r)

    return {"message": f"Ingestion of {len(articles)} documents has been started"}

class SearchResponse(BaseModel):
    results: dict

@app.get("/search", response_model=SearchResponse)
async def search(
    query: str = Query(..., description="The search query"),
    do_hybrid_search: bool = Query(False, description="Whether to perform hybrid search")
):
    logger.info(f"Performing search with query: {query}, hybrid_search: {do_hybrid_search}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "http://r2r:8000/v1/search",
                json={
                    "query": query,
                    "do_hybrid_search": do_hybrid_search
                },
                timeout=30.0  # Adjust timeout as needed
            )
            response.raise_for_status()
            return SearchResponse(results=response.json())
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred during search: {e}")
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except httpx.RequestError as e:
            logger.error(f"Error communicating with R2R service during search: {e}")
            raise HTTPException(status_code=500, detail=f"Error communicating with R2R service: {str(e)}")

@app.post("/rag")
async def rag(
    query: str = Body(..., description="The RAG query"),
    do_hybrid_search: bool = Body(False, description="Whether to perform hybrid search"),
    stream: bool = Body(False, description="Whether to stream the response")
):
    logger.info(f"Performing RAG with query: {query}, hybrid_search: {do_hybrid_search}, stream: {stream}")
    async def event_stream():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                "http://r2r:8000/v1/rag",
                json={
                    "query": query,
                    "do_hybrid_search": do_hybrid_search,
                    "stream": True
                },
                timeout=30.0
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    if stream:
        return StreamingResponse(event_stream(), media_type="application/json")
    else:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "http://r2r:8000/v1/rag",
                    json={
                        "query": query,
                        "do_hybrid_search": do_hybrid_search,
                        "stream": False
                    },
                    timeout=30.0  # Adjust timeout as needed
                )
                response.raise_for_status()
                return SearchResponse(results=response.json())
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error occurred during RAG: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except httpx.RequestError as e:
                logger.error(f"Error communicating with R2R service during RAG: {e}")
                raise HTTPException(status_code=500, detail=f"Error communicating with R2R service: {str(e)}")
