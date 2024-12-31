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
    Content, ContentEvaluation, XClassification,
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

