import os
import json
import logging
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, Depends, APIRouter
from sqlmodel import select, update, delete
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import pandas as pd
from io import StringIO
from fastapi.responses import StreamingResponse

from core.utils import logger
from core.adb import get_session
from core.models import (
    Content, ContentClassification, ContentEntity, ContentTag, Entity, EntityLocation,
    Location, Tag
)

router = APIRouter()

########################################################################################
## HELPER FUNCTIONS

@router.post("/deduplicate_contents")
async def deduplicate_contents(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            # Find duplicate contents based on URL
            query = select(Content.url, func.count(Content.url)).group_by(Content.url).having(func.count(Content.url) > 1)
            result = await session.execute(query)
            duplicates = result.fetchall()

            for url, count in duplicates:
                # Keep one content and delete the rest
                subquery = (
                    select(Content.id)
                    .where(Content.url == url)
                    .order_by(Content.insertion_date.desc())
                    .offset(1)
                )
                delete_query = delete(Content).where(Content.id.in_(subquery))
                await session.execute(delete_query)
                logger.info(f"Deleted duplicates for URL: {url}")

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
            # Delete all records from the ContentClassification table
            await session.execute(delete(ContentClassification))
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
        logger.error(f"Error deleting embeddings: {e}", exc_info=True)
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

@router.get("/contents_csv_full")
async def get_contents_csv_full(session: AsyncSession = Depends(get_session)):
    try:
        async with session.begin():
            query = select(Content).options(
                selectinload(Content.entities).selectinload(Entity.locations),
                selectinload(Content.tags),
                selectinload(Content.classification)
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
                "classification": content.classification.dict() if content.classification else None
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

        return StreamingResponse(csv_buffer, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=contents_full.csv"})

    except Exception as e:
        logger.error(f"Error generating CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating CSV")
