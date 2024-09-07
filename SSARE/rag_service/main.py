from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel, select
from sqlalchemy.orm import selectinload
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from bcore.service_mapping import ServiceConfig
from bcore.models import Article, Entity, Location
from bcore.adb import engine as articles_engine, get_session as get_articles_session
import tempfile
import os
from fastapi import APIRouter
from pydantic import BaseModel
import logging
from fastapi.responses import StreamingResponse
from r2r import R2RClient
from datetime import datetime

app = FastAPI()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load configuration
config = ServiceConfig()

# Database setup for pgvector (R2R vector storage)
PGVECTOR_URL = (
    f"postgresql+asyncpg://{config.R2R_DB_USER}:{config.R2R_DB_PASSWORD}"
    f"@r2r_database:{config.R2R_DB_PORT}/{config.R2R_DB_NAME}"
)
pgvector_engine = create_async_engine(PGVECTOR_URL)

# R2R client
r2r_client = R2RClient("http://r2r:8001")

# Ingestion status tracking
last_ingestion_status = {"status": "Not run", "timestamp": None, "message": None}

@app.get("/healthz")
async def healthcheck():
    return {"message": "RAG Service Running"}, 200

@app.get("/articles/", response_model=List[Article])
async def read_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_articles_session)):
    logger.info(f"Fetching articles with skip={skip} and limit={limit}")
    statement = select(Article).offset(skip).limit(limit)
    result = await db.execute(statement)
    db_articles = result.scalars().all()
    return db_articles

async def get_articles(skip: int = 0, limit: int = 10, db: AsyncSession = Depends(get_articles_session)):
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
async def ingest_documents(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_articles_session)):
    logger.info("Starting document ingestion")
    global last_ingestion_status

    async def send_to_r2r():
        global last_ingestion_status
        file_paths = []
        try:
            async with AsyncSession(articles_engine) as session:
                statement = select(Article).options(
                    selectinload(Article.entities).selectinload(Entity.locations)
                ).limit(100)
                result = await session.execute(statement)
                articles = result.scalars().all()

                print(articles[:3])

                metadatas = []

                for article in articles:
                    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as temp_file:
                        temp_file.write(article.paragraphs)
                        file_paths.append(temp_file.name)

                    metadata = {
                        "title": article.headline,
                        "url": article.url,
                        "published_by": str(article.source),
                        "entities": [{"name": e.name, "type": e.entity_type} for e in article.entities]
                    }
                    metadatas.append(metadata)

                ingest_response = r2r_client.ingest_files(
                    file_paths=file_paths,
                    metadatas=metadatas,
                )
                
                if isinstance(ingest_response, dict) and 'error' in ingest_response:
                    raise Exception(f"R2R ingestion failed: {ingest_response['error']}")
                
                last_ingestion_status = {
                    "status": "Success",
                    "timestamp": datetime.now().isoformat(),
                    "message": f"Successfully ingested {len(articles)} documents to R2R"
                }
                logger.info(last_ingestion_status["message"])

        except Exception as e:
            error_message = f"An error occurred during R2R ingestion: {e}"
            last_ingestion_status = {
                "status": "Failed",
                "timestamp": datetime.now().isoformat(),
                "message": error_message
            }
            logger.error(error_message)
        finally:
            for file_path in file_paths:
                os.unlink(file_path)

    background_tasks.add_task(send_to_r2r)

    return {"message": "Ingestion of documents has been started"}

@app.get("/ingestion_status")
async def get_ingestion_status():
    return last_ingestion_status

class SearchResponse(BaseModel):
    results: dict

@app.post("/search", response_model=SearchResponse)
async def search(
    query: str = Query(..., description="The search query"),
    do_hybrid_search: bool = Query(False, description="Whether to perform hybrid search"),
    db: AsyncSession = Depends(get_articles_session)
):
    logger.info(f"Performing search with query: {query}, hybrid_search: {do_hybrid_search}")
    try:
        search_response = r2r_client.search(
            query,
            vector_search_settings={
                "use_hybrid_search": do_hybrid_search,
                "search_limit": 10
            }
        )

        results = []
        for result in search_response['results']:
            article = await db.execute(select(Article).where(Article.url == result['metadata']['url']))
            article = article.scalar_one_or_none()
            if article:
                result['entities'] = [{"name": e.name, "type": e.entity_type} for e in article.entities]
                result['locations'] = [{"name": l.name, "type": l.type, "coordinates": l.coordinates} for e in article.entities for l in e.locations]
            results.append(result)

        return SearchResponse(results={"results": results})
    except Exception as e:
        logger.error(f"Error during search: {e}")
        raise HTTPException(status_code=500, detail=f"Error during search: {str(e)}")

@app.post("/rag")
async def rag(
    query: str = Body(..., description="The RAG query"),
    do_hybrid_search: bool = Body(False, description="Whether to perform hybrid search"),
    stream: bool = Body(False, description="Whether to stream the response"),
    db: AsyncSession = Depends(get_articles_session)
):
    logger.info(f"Performing RAG with query: {query}, hybrid_search: {do_hybrid_search}, stream: {stream}")
    try:
        rag_response = r2r_client.rag(
            query,
            vector_search_settings={"use_hybrid_search": do_hybrid_search},
            rag_generation_config={"stream": stream}
        )

        if stream:
            return StreamingResponse(rag_response, media_type="application/json")
        else:
            for chunk in rag_response['source_chunks']:
                article = await db.execute(select(Article).where(Article.url == chunk['metadata']['url']))
                article = article.scalar_one_or_none()
                if article:
                    chunk['entities'] = [{"name": e.name, "type": e.entity_type} for e in article.entities]
                    chunk['locations'] = [{"name": l.name, "type": l.type, "coordinates": l.coordinates} for e in article.entities for l in e.locations]

            return rag_response
    except Exception as e:
        logger.error(f"Error during RAG: {e}")
        raise HTTPException(status_code=500, detail=f"Error during RAG: {str(e)}")

class DocumentsOverviewRequest(BaseModel):
    document_ids: Optional[List[str]] = None
    user_ids: Optional[List[str]] = None

@app.get("/documents_overview")
async def get_documents_overview(request: DocumentsOverviewRequest = Depends()):
    logger.info(f"Fetching documents overview for document_ids: {request.document_ids}, user_ids: {request.user_ids}")
    try:
        overview_response = r2r_client.documents_overview(
            document_ids=request.document_ids,
            user_ids=request.user_ids
        )
        return overview_response
    except Exception as e:
        logger.error(f"Error fetching documents overview: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching documents overview: {str(e)}")

class DeleteRequest(BaseModel):
    document_ids: Optional[List[str]] = None
    user_ids: Optional[List[str]] = None
    delete_all: bool = False

@app.delete("/delete")
async def delete_documents(delete_request: DeleteRequest):
    try:
        if delete_request.delete_all:
            logger.info("Fetching all document IDs for deletion")
            all_docs = r2r_client.documents_overview()
            document_ids = [doc['id'] for doc in all_docs['results']]
            logger.info(f"Deleting all {len(document_ids)} documents")
        else:
            document_ids = delete_request.document_ids
            logger.info(f"Deleting documents with document_ids: {document_ids}, user_ids: {delete_request.user_ids}")

        delete_response = r2r_client.delete(
            document_ids=document_ids,
            user_ids=delete_request.user_ids
        )
        return delete_response
    except Exception as e:
        logger.error(f"Error during document deletion process: {e}")
        raise HTTPException(status_code=500, detail=f"Error during document deletion process: {str(e)}")
