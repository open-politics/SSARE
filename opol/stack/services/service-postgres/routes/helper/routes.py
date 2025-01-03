import os
import json
import logging
from typing import List, Optional, Dict, Any, AsyncGenerator
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks, Query, Body
from sqlmodel import SQLModel, Field, create_engine, Session, select, update
from sqlmodel import Column, JSON
from contextlib import asynccontextmanager
from enum import Enum
import httpx
import math
import pandas as pd
import uuid
from io import StringIO

from fastapi import Query, APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from sqlalchemy import and_, delete, func, insert, or_, text, update
from sqlalchemy import inspect
from sqlalchemy import desc
from sqlalchemy import join
from sqlalchemy import alias, distinct
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import joinedload, selectinload
from sqlmodel import Session
from typing import AsyncGenerator
from core.utils import logger
from core.adb import engine, get_session, create_db_and_tables
from core.middleware import add_cors_middleware
from core.models import Content, ContentEntity, ContentTag, Entity, EntityLocation, Location, Tag, ContentEvaluation, MediaDetails
from core.service_mapping import ServiceConfig

# App API Router
router = APIRouter()

# Config
config = ServiceConfig()

########################################################################################
## HELPER FUNCTIONS

@router.post("/deduplicate_contents")
async def deduplicate_contents(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Content).group_by(Content.id, Content.url).having(func.count() > 1)
            result = await session.execute(query)
            duplicate_contents = result.scalars().all()

        for content in duplicate_contents:
            logger.info(f"Duplicate content: {content.url}")
            await session.delete(content)

        await session.commit()
        return {"message": "Duplicate contents deleted successfully."}
    except Exception as e:
        logger.error(f"Error deduplicating contents: {e}")
        raise HTTPException(status_code=500, detail=str(e))

#### MISC

@router.delete("/delete_all_classifications")
async def delete_all_classifications(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            # Delete all records from the ContentEvaluation table
            await session.execute(delete(ContentEvaluation))
            await session.commit()
            logger.info("All classifications deleted successfully.")
            return {"message": "All classifications deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting classifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error deleting classifications")

@router.delete("/delete_all_embeddings")
async def delete_all_embeddings(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            # Delete all embeddings from all contents
            await session.execute(update(Content).values(embeddings=None))
            await session.commit()
            logger.info("All embeddings deleted successfully.")
            return {"message": "All embeddings deleted successfully."}
    except Exception as e:
        logger.error(f"Error deleting embeddings: {e}")
        raise HTTPException(status_code=500, detail="Error deleting embeddings")

@router.get("/contents_csv_quick")
async def get_contents_csv_quick(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Content.id, Content.url, Content.title, Content.source, Content.insertion_date)
            result = await session.execute(query)
            contents = result.fetchall()

        # Create a DataFrame
        df = pd.DataFrame(contents, columns=['id', 'url', 'title', 'source', 'insertion_date'])

        # Convert DataFrame to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=contents_quick.csv"})

    except Exception as e:
        logger.error(f"Error generating quick CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating quick CSV")
    
async def get_contents_csv(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Content)
            result = await session.execute(query)
            contents = result.scalars().all()

        # Convert contents to a list of dictionaries
        contents_data = [content.dict() for content in contents]

        # Create a DataFrame
        df = pd.DataFrame(contents_data)

        # Convert DataFrame to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=contents.csv"})

    except Exception as e:
        logger.error(f"Error generating CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating CSV")

@router.get("/contents_csv_full")
async def get_contents_csv(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Content).options(
                selectinload(Content.entities).selectinload(Entity.locations),
                selectinload(Content.tags),
                selectinload(Content.evaluation)
            )
            result = await session.execute(query)
            contents = result.scalars().all()

        # Convert contents to a list of dictionaries
        contents_data = []
        for content in contents:
            content_dict = {
                "id": str(content.id),
                "url": content.url,
                "title": content.title,
                "source": content.source,
                "insertion_date": content.insertion_date.isoformat() if content.insertion_date else None,
                "text_content": content.text_content,
                "embeddings": content.embeddings.tolist() if content.embeddings is not None else None,
                "entities": [
                    {
                        "id": str(e.id),
                        "name": e.name,
                        "entity_type": e.entity_type,
                        "locations": [
                            {
                                "name": loc.name,
                                "type": loc.type,
                                "coordinates": loc.coordinates.tolist() if loc.coordinates is not None else None
                            } for loc in e.locations
                        ] if e.locations else []
                    } for e in content.entities
                ] if content.entities else [],
                "tags": [
                    {
                        "id": str(t.id),
                        "name": t.name
                    } for t in (content.tags or [])
                ],
                "evaluation": content.evaluation.dict() if content.evaluation else None
            }
            contents_data.append(content_dict)

        # Flatten the data for CSV
        flattened_data = []
        for content in contents_data:
            base_data = {
                "id": content["id"],
                "url": content["url"],
                "title": content["title"],
                "source": content["source"],
                "insertion_date": content["insertion_date"],
                "text_content": content["text_content"],
                "embeddings": content["embeddings"],
            }
            if content["entities"]:
                for entity in content["entities"]:
                    entity_data = {
                        "entity_id": entity["id"],
                        "entity_name": entity["name"],
                        "entity_type": entity["entity_type"],
                        "locations": json.dumps(entity["locations"]),
                    }
                    flattened_data.append({**base_data, **entity_data})
            else:
                flattened_data.append(base_data)

        # Create a DataFrame
        df = pd.DataFrame(flattened_data)

        # Convert DataFrame to CSV
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=contents.csv"})

    except Exception as e:
        logger.error(f"Error generating CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating CSV")

@router.get("/contents_with_chunks")
async def get_contents_with_chunks(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            # Query contents and eagerly load chunks
            query = select(Content).options(selectinload(Content.chunks))
            result = await session.execute(query)
            contents = result.scalars().all()

        contents_with_chunks = []
        for content in contents:
            if content.chunks:
                content_data = {
                    "id": str(content.id),
                    "url": content.url,
                    "title": content.title,
                    "source": content.source,
                    "insertion_date": content.insertion_date if content.insertion_date else None,
                    "chunks": [
                        {
                            "chunk_number": chunk.chunk_number,
                            "text": chunk.text,
                            "embeddings": chunk.embeddings
                        } for chunk in content.chunks
                    ]
                }
                contents_with_chunks.append(content_data)

        return contents_with_chunks

    except Exception as e:
        logger.error(f"Error retrieving contents with chunks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error retrieving contents with chunks")

@router.post("/fix_and_purge_null_content_type")
async def fix_and_purge_null_content_type(session: AsyncSession = Depends(get_session)):
    """
    Fixes entries with NULL content_type by setting a default value and purges any remaining NULL entries.
    """
    try:
        async with session.begin():
            # Fix entries where content_type is NULL by setting a default value
            fix_stmt = (
                update(Content)
                .where(Content.content_type == None)
                .values(content_type='default_type')  # Replace 'default_type' with an appropriate value
            )
            result = await session.execute(fix_stmt)
            fixed_count = result.rowcount
            logger.info(f"Fixed {fixed_count} entries with NULL content_type by setting a default value.")

            # Purge any remaining entries with NULL content_type, if any
            purge_stmt = select(Content).where(Content.content_type == None)
            result = await session.execute(purge_stmt)
            contents_to_purge = result.scalars().all()
            purge_count = len(contents_to_purge)

            for content in contents_to_purge:
                await session.delete(content)

            if purge_count > 0:
                logger.info(f"Purged {purge_count} additional articles with NULL content_type.")
                purge_message = f"Purged {purge_count} articles with NULL content_type successfully."
            else:
                purge_message = "No additional articles found with NULL content_type to purge."

        await session.commit()
        return {
            "message": f"Fixed {fixed_count} entries with NULL content_type and {purge_message}"
        }
    except Exception as e:
        logger.error(f"Error fixing and purging articles: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail="Failed to fix and purge articles with NULL content_type.")


@router.delete("/clear_filtered_out_queue")
async def clear_filtered_out_queue():
    try:
        redis_conn = Redis(host='redis', port=ServiceConfig.REDIS_PORT, db=4)
        redis_conn.delete('filtered_out_queue')
        return {"message": "Filtered out queue cleared successfully"}
    except Exception as e:
        logger.error(f"Error clearing filtered out queue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error clearing filtered out queue")

@router.get("/read_filtered_out_queue")
async def read_filtered_out_queue():
    try:
        redis_conn = Redis(host='redis', port=ServiceConfig.REDIS_PORT, db=4)
        filtered_out_contents = redis_conn.lrange('filtered_out_queue', 0, -1)
        
        # Convert bytes to JSON objects
        contents = [json.loads(content) for content in filtered_out_contents]
        
        return {"filtered_out_contents": contents}
    except Exception as e:
        logger.error(f"Error reading filtered out queue: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error reading filtered out queue")

@router.get("/dump_contents")
async def dump_contents(session: AsyncSession = Depends(get_session)) -> List[dict]:
    """Dump all contents with selected fields."""
    async with session.begin():
        query = select(Content)
        result = await session.execute(query)
        contents = result.scalars().all()

    # Prepare the dumped data
    dumped_contents = [
        {
            "url": content.url,
            "title": content.title,
            "text_content": content.text_content,
            "source": content.source,
            "content_type": content.content_type,
            "insertion_date": content.insertion_date
        }
        for content in contents
    ]

    return dumped_contents

@router.post("/ingest_json_backup")
async def ingest_json_backup(
    contents: List[Dict[str, Any]] = Body(...),
    session: AsyncSession = Depends(get_session)
):
    """
    Ingests JSON backups and saves them to the database using the Content model.
    """
    try:
        async with session.begin():
            for content_data in contents:
                # Check if content with the same URL already exists
                existing_content = await session.execute(
                    select(Content).where(Content.url == content_data.get("url"))
                )
                if existing_content.scalar_one_or_none() is None:
                    # Create a Content instance
                    content = Content(
                        url=content_data.get("url"),
                        title=content_data.get("title"),
                        text_content=content_data.get("text_content"),
                        source=content_data.get("source"),
                        content_type=content_data.get("content_type"),
                        insertion_date=content_data.get("insertion_date")
                    )
                    session.add(content)
                else:
                    logger.info(f"Content with URL {content_data.get('url')} already exists. Skipping.")

            await session.commit()
            logger.info("JSON backup ingested successfully.")
            return {"message": "JSON backup ingested successfully."}
    except Exception as e:
        logger.error(f"Error ingesting JSON backup: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail="Error ingesting JSON backup")

# @router.post("/restore_dates_from_backup")
# async def restore_dates_from_backup(
#     backup_path: str = "/.backups",
#     session: AsyncSession = Depends(get_session)
# ):
#     """
#     Restores original insertion dates from backup files while preserving all other current data.
#     """
#     import os
#     from datetime import datetime

#     try:
#         # Find all JSON files in backup directory
#         backup_files = [f for f in os.listdir(backup_path) if f.endswith('.json')]
#         if not backup_files:
#             return {"message": "No backup files found"}

#         date_updates = 0
#         errors = []

#         async with session.begin():
#             for backup_file in backup_files:
#                 try:
#                     with open(os.path.join(backup_path, backup_file), 'r') as f:
#                         backup_contents = json.load(f)

#                     # Create a mapping of URLs to original dates
#                     original_dates = {
#                         content['url']: datetime.fromisoformat(content['insertion_date'])
#                         for content in backup_contents 
#                         if content.get('url') and content.get('insertion_date')
#                     }

#                     # Update dates for existing contents
#                     for url, original_date in original_dates.items():
#                         result = await session.execute(
#                             update(Content)
#                             .where(Content.url == url)
#                             .values(insertion_date=original_date)
#                             .returning(Content.id)
#                         )
#                         if result.scalar_one_or_none():
#                             date_updates += 1
#                             logger.info(f"Restored date for {url}: {original_date}")

#                 except Exception as e:
#                     errors.append(f"Error processing {backup_file}: {str(e)}")
#                     logger.error(f"Error processing backup file {backup_file}: {e}", exc_info=True)

#         await session.commit()
        
#         return {
#             "message": f"Date restoration complete. Updated {date_updates} articles.",
#             "errors": errors if errors else None
#         }

#     except Exception as e:
#         logger.error(f"Error restoring dates: {e}", exc_info=True)
#         await session.rollback()
#         raise HTTPException(status_code=500, detail=str(e))

#healthz
@router.get("/healthz")
async def healthz():
    return {"status": "ok"}, 200

@router.get("/bbc_article_urls")
async def get_bbc_article_urls(
    limit: int = Query(10, description="Number of BBC articles to return"),
    session: AsyncSession = Depends(get_session)
):
    """
    Fetches URLs of BBC articles from the database.
    """
    try:
        async with session.begin():
            query = (
                select(Content.url)
                .where(Content.source == 'bbc')
                .limit(limit)
            )
            result = await session.execute(query)
            urls = result.scalars().all()
            
            return {"urls": urls}
            
    except Exception as e:
        logger.error(f"Error fetching BBC article URLs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching BBC article URLs")

@router.post("/update_articles")
async def update_articles(
    source: str = Query(..., description="Source to update (bbc, dw or cnn)"), 
    limit: int = Query(..., description="how many of them"),
    session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            # Fetch articles based on source
            url_pattern = '%www.bbc.com%' if source == 'bbc' else '%dw.com%' if source == 'dw' else '%www.cnn.com%'
            query = select(Content).options(selectinload(Content.media_details)).where(
                Content.url.ilike(url_pattern)
            )
            result = await session.execute(query)
            contents = result.scalars().all()

        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            for content in contents:
                if content.url and '/video' not in content.url:
                    logger.info(f"Processing {source} article: {content.url}")
                    response = await client.post(
                        "http://service-scraper:8081/scrape_article",
                        params={"url": content.url}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        logger.error(data)
                        async with session.begin():
                            content.url = data.get("url") if data.get("url") else None
                            content.publication_date = data.get("publication_date")
                            content.source = source
                            content.text_content = data.get("text_content")
                            content.summary = data.get("summary") if data.get("summary") else None
                            content.meta_summary = data.get("meta_summary") if data.get("meta_summary") else None
                            if content.media_details:
                                content.media_details.top_image = data.get("top_image")
                            else:
                                content.media_details = MediaDetails(top_image=data.get("top_image"))
                            await session.flush()
                    else:
                        logger.error(f"Failed to scrape {content.url}: {response.text}")
                else:
                    logger.error("Encountered an empty URL or Video, skipping.")

        await session.commit()
        return {"message": f"{source.upper()} articles updated successfully."}
    except Exception as e:
        logger.error(f"Error updating {source} articles: {e}", exc_info=True)
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating {source} articles")
    
@router.get("/articles_with_top_image")
async def get_articles_with_top_image(session: AsyncSession = Depends(get_session)):
    """
    Retrieve articles where the top image is not empty, returning article data and top image URL.
    """
    try:
        async with session.begin():
            query = (
                select(Content, MediaDetails.top_image)
                .join(Content.media_details)
                .where(MediaDetails.top_image.isnot(None))
            )
            result = await session.execute(query)
            articles_with_images = result.all()

            articles_data = []
            for article, top_image in articles_with_images:
                article_dict = article.dict()
                article_dict["top_image"] = top_image
                articles_data.append(article_dict)

        return {"articles": articles_data}
    except Exception as e:
        logger.error(f"Error retrieving articles with top image: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving articles with top image")


@router.get("/failed_geocodes")
async def get_failed_geocodes():
    try:
        redis_conn = await Redis.from_url(get_redis_url(), db=6, decode_responses=True)
        failed_geocodes = await redis_conn.lrange('failed_geocodes_queue', 0, -1)
        failed_locations = [json.loads(fail) for fail in failed_geocodes]
        await redis_conn.close()
        return {"failed_geocodes": failed_locations}
    except Exception as e:
        logger.error(f"Error retrieving failed geocodes: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))