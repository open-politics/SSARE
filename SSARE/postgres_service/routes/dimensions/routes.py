from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
from sqlalchemy import and_, func, or_, desc, distinct, exists
import httpx
import json

from core.adb import get_session
from core.models import (
    Content, ContentClassification, XClassification,
    Entity, Location, ClassificationDimension
)
from core.utils import logger, UUIDEncoder, DimensionRequestEncoder

router = APIRouter()

class ContentFilter(BaseModel):
    source: Optional[str] = None
    entity_name: Optional[str] = None
    location_name: Optional[str] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None

class DimensionRequest(BaseModel):
    name: str
    description: str
    type: str

async def serialize_content(content):
    """Helper function to safely serialize content"""
    return {
        "id": str(content.id),
        "url": content.url,
        "title": content.title,
        "text_content": content.text_content,
        "source": content.source,
        "insertion_date": content.insertion_date,
    }

@router.post("/analyze_contents")
async def analyze_contents(
    filters: ContentFilter,
    new_dimensions: Optional[List[DimensionRequest]] = None,
    existing_dimension_names: Optional[List[str]] = None,
    limit: Optional[int] = Query(None, ge=1, description="Maximum number of articles to analyze"),
    session: AsyncSession = Depends(get_session)
):
    """
    Analyze contents based on filters and optionally apply new classifications.
    
    1. Query contents using provided filters
    2. Return existing classifications
    3. Optionally apply new dynamic classifications
    """
    try:
        # Create new dimensions first if provided
        if new_dimensions:
            for dim_request in new_dimensions:
                try:
                    # Check if dimension exists
                    result = await session.execute(
                        select(ClassificationDimension)
                        .where(ClassificationDimension.name == dim_request.name)
                    )
                    existing_dim = result.scalar_one_or_none()
                    
                    if not existing_dim:
                        dimension = ClassificationDimension(
                            name=dim_request.name,
                            type=dim_request.type,
                            description=dim_request.description
                        )
                        session.add(dimension)
                
                except Exception as e:
                    logger.error(f"Error creating dimension {dim_request.name}: {e}")
                    raise HTTPException(status_code=400, detail=f"Error creating dimension: {str(e)}")
            
            await session.commit()

        # Build base query with eager loading
        query = (
            select(Content)
            .options(
                selectinload(Content.classification),
                selectinload(Content.xclassifications),
                selectinload(Content.entities),
                selectinload(Content.entities).selectinload(Entity.locations)
            )
            .distinct()
        )

        # Apply filters
        if filters.source:
            query = query.where(Content.source == filters.source)
        if filters.entity_name:
            query = query.join(Content.entities).where(Entity.name == filters.entity_name)
        if filters.location_name:
            query = query.join(Content.entities).join(Entity.locations).where(Location.name == filters.location_name)
        if filters.from_date:
            query = query.where(Content.insertion_date >= filters.from_date.isoformat())
        if filters.to_date:
            query = query.where(Content.insertion_date <= filters.to_date.isoformat())

        # Ensure limit is applied as integer
        if limit is not None:
            query = query.limit(int(limit))

        # Execute query
        result = await session.execute(query)
        contents = result.scalars().all()
        
        if limit:
            contents = contents[:limit]

        # Format response with existing classifications
        content_analyses = []
        for content in contents:
            try:
                # Get existing classifications for this content
                existing_classifications = await session.execute(
                    select(XClassification)
                    .where(XClassification.content_id == content.id)
                )
                existing_class_map = {
                    (x.content_id, x.dimension_id): x 
                    for x in existing_classifications.scalars().all()
                }

                # Serialize content safely
                content_dict = await serialize_content(content)
                classification_request = {
                    "content": content_dict,
                    "dimensions": [dim.dict() for dim in new_dimensions] if new_dimensions else None,
                    "dimension_names": existing_dimension_names
                }

                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://classification_service:5688/test_dynamic_classification",
                        json=classification_request,
                        headers={"Content-Type": "application/json"},
                        timeout=60.0
                    )
                    response.raise_for_status()
                    
                response_data = response.json()
                classifications = response_data["classifications"]
                
                # Process classifications
                for dim_name, value in classifications.items():
                    dim_result = await session.execute(
                        select(ClassificationDimension)
                        .where(ClassificationDimension.name == dim_name)
                    )
                    dimension = dim_result.scalar_one_or_none()
                    
                    if dimension:
                        # Check if classification already exists
                        existing_class = existing_class_map.get((content.id, dimension.id))
                        
                        if existing_class:
                            # Update existing classification
                            existing_class.value = value
                            session.add(existing_class)
                        else:
                            # Create new classification
                            xclass = XClassification(
                                content_id=content.id,
                                dimension_id=dimension.id,
                                value=value
                            )
                            session.add(xclass)
                
                # Commit after each content to prevent large transaction rollbacks
                await session.commit()
                
                content_analyses.append({
                    "content_id": str(content.id),
                    "url": content.url,
                    "title": content.title,
                    "text_content": content.text_content[:100],
                    "classifications": classifications
                })

                # Early return if we've reached the limit
                if limit and len(content_analyses) >= limit:
                    break

            except Exception as e:
                # Rollback the session for this content's transaction
                await session.rollback()
                logger.error(f"Error processing content {content.url}: {str(e)}", exc_info=True)
                content_analyses.append({
                    "content_id": str(content.id),
                    "url": content.url,
                    "error": str(e)
                })

                # Early return if we've reached the limit even with an error
                if limit and len(content_analyses) >= limit:
                    break

        return {

            "total_processed": len(content_analyses),
            "analyses": content_analyses
        }

    except Exception as e:
        await session.rollback()
        logger.error(f"Error analyzing contents: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

## List all dimensions, each with the number of contents that this dimension is classified with and 2 example contents (title), the score of that content and for each diimension the average 
from typing import List
from pydantic import BaseModel
from uuid import UUID
class DimensionWithCount(BaseModel):
    id: UUID # UUID
    name: str
    description: str
    type: str
    content_count: int
    example_contents: List[str]

@router.get("/dimensions", response_model=List[DimensionWithCount])
async def list_dimensions(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(
            ClassificationDimension,
            func.count(distinct(Content.id)).label('content_count'),
            func.array_agg(Content.title).label('example_contents')
        )
        .join(XClassification, ClassificationDimension.id == XClassification.dimension_id)
        .join(Content, XClassification.content_id == Content.id)
        .group_by(ClassificationDimension.id)
    )
    dimensions = result.all()
    return [
        DimensionWithCount(
            id=dim.id,
            name=dim.name,
            description=dim.description,
            type=dim.type,
            content_count=count,
            example_contents=example_contents
        )
        for dim, count, example_contents in dimensions
    ]