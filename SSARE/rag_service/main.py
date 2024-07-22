from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from core.service_mapping import ServiceConfig
from core.models import Article
import tempfile
import io
import os
from fastapi import APIRouter
from pydantic import BaseModel
import httpx
import json
import logging
from fastapi.responses import StreamingResponse
from typing import List, Optional, Union

app = FastAPI()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config = ServiceConfig()

# Database setup for main PostgreSQL
DATABASE_URL = (
    f"postgresql+asyncpg://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
    f"@postgres_service:{config.ARTICLES_DB_PORT}/{config.ARTICLES_DB_NAME}"
)
engine = create_async_engine(DATABASE_URL)

# Database setup for pgvector (R2R vector storage)
PGVECTOR_URL = (
    f"postgresql+asyncpg://{config.R2R_DB_USER}:{config.R2R_DB_PASSWORD}"
    f"@r2r_db:{config.R2R_DB_PORT}/{config.R2R_DB_NAME}"
)
pgvector_engine = create_async_engine(PGVECTOR_URL)

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

@app.get("/articles/", response_model=List[Article])
async def read_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    logger.info(f"Fetching articles with skip={skip} and limit={limit}")
    statement = select(Article).offset(skip).limit(limit)
    result = await db.execute(statement)
    db_articles = result.scalars().all()
    return db_articles

async def get_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_db)):
    logger.info(f"Getting articles with skip={skip} and limit={limit}")
    statement = select(Article).offset(skip).limit(limit)
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
    articles = await get_articles(limit=100, db=db)

    async def send_to_r2r():
        async with httpx.AsyncClient() as client:
            try:
                files = []
                metadatas = []

                for i, article in enumerate(articles):
                    content = io.StringIO(article.paragraphs)
                    files.append(("files", (f"article_{i}.txt", content, "text/plain")))

                    metadata = {
                        "title": article.headline,
                        "url": article.url,
                        "published_by": str(article.source),
                        "entities": json.loads(article.entities) if article.entities else [],
                        "geocodes": article.geocodes if article.geocodes else []
                    }
                    metadatas.append(metadata)

                response = await client.post(
                    "http://r2r:8000/v1/ingest_files",
                    files=files,
                    data={"metadatas": json.dumps(metadatas)},
                    timeout=30.0
                )
                response.raise_for_status()
                logger.info(f"Successfully ingested {len(articles)} documents to R2R")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error occurred during ingestion: {e}")
            except httpx.RequestError as e:
                logger.error(f"An error occurred while requesting ingestion: {e}")
            finally:
                for _, (_, content, _) in files:
                    content.close()

    background_tasks.add_task(send_to_r2r)

    return {"message": f"Ingestion of {len(articles)} documents has been started"}

class SearchResponse(BaseModel):
    results: dict

@app.post("/search", response_model=SearchResponse)
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
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Search successful. Result: {result}")
            return SearchResponse(results=result)
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred during search: {e}")
            logger.error(f"Response content: {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Error from R2R service: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Error communicating with R2R service during search: {e}")
            raise HTTPException(status_code=500, detail=f"Error communicating with R2R service: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during search: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

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
                    timeout=30.0
                )
                response.raise_for_status()
                return SearchResponse(results=response.json())
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error occurred during RAG: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except httpx.RequestError as e:
                logger.error(f"Error communicating with R2R service during RAG: {e}")
                raise HTTPException(status_code=500, detail=f"Error communicating with R2R service: {str(e)}")

class DocumentsOverviewRequest(BaseModel):
    document_ids: Optional[List[str]] = None
    user_ids: Optional[List[str]] = None

@app.get("/documents_overview")
async def get_documents_overview(request: DocumentsOverviewRequest = Depends()):
    logger.info(f"Fetching documents overview for document_ids: {request.document_ids}, user_ids: {request.user_ids}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "http://r2r:8000/v1/documents_overview",
                params=request.dict(exclude_none=True),
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred while fetching documents overview: {e}")
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except httpx.RequestError as e:
            logger.error(f"Error communicating with R2R service while fetching documents overview: {e}")
            raise HTTPException(status_code=500, detail=f"Error communicating with R2R service: {str(e)}")

class DeleteRequest(BaseModel):
    document_ids: Optional[List[str]] = None
    user_ids: Optional[List[str]] = None
    delete_all: bool = False

@app.delete("/delete")
async def delete_documents(delete_request: DeleteRequest):
    async with httpx.AsyncClient() as client:
        try:
            if delete_request.delete_all:
                logger.info("Fetching all document IDs for deletion")
                overview_response = await client.get(
                    "http://r2r:8000/v1/documents_overview",
                    timeout=30.0
                )
                overview_response.raise_for_status()
                all_docs = overview_response.json()
                document_ids = [doc['id'] for doc in all_docs['results']]
                logger.info(f"Deleting all {len(document_ids)} documents")
            else:
                document_ids = delete_request.document_ids
                logger.info(f"Deleting documents with document_ids: {document_ids}, user_ids: {delete_request.user_ids}")

            delete_payload = {
                "document_ids": document_ids,
                "user_ids": delete_request.user_ids
            }
            delete_response = await client.delete(
                "http://r2r:8000/v1/delete",
                json={k: v for k, v in delete_payload.items() if v is not None},
                timeout=30.0
            )
            delete_response.raise_for_status()
            return delete_response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred during document deletion process: {e}")
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except httpx.RequestError as e:
            logger.error(f"Error communicating with R2R service during document deletion process: {e}")
            raise HTTPException(status_code=500, detail=f"Error communicating with R2R service: {str(e)}")