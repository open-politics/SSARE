from typing import List, Optional, Union, Literal
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, Text, ARRAY
from pgvector.sqlalchemy import Vector
import uuid
from enum import Enum
from sqlalchemy.dialects.postgresql import JSONB
from pydantic import BaseModel, ValidationError, field_validator
import json

class BaseModel(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

# Association Tables
class ContentEntity(SQLModel, table=True):
    content_id: uuid.UUID = Field(foreign_key="content.id", primary_key=True)
    entity_id: uuid.UUID = Field(foreign_key="entity.id", primary_key=True)
    frequency: int = Field(default=1)

class ContentTag(SQLModel, table=True):
    content_id: uuid.UUID = Field(foreign_key="content.id", primary_key=True)
    tag_id: uuid.UUID = Field(foreign_key="tag.id", primary_key=True)

class EntityLocation(SQLModel, table=True):
    entity_id: uuid.UUID = Field(foreign_key="entity.id", primary_key=True)
    location_id: uuid.UUID = Field(foreign_key="location.id", primary_key=True)

class ContentTopic(SQLModel, table=True):
    content_id: uuid.UUID = Field(foreign_key="content.id", primary_key=True)
    topic_id: uuid.UUID = Field(foreign_key="topic.id", primary_key=True)

# Core Models
class Content(BaseModel, table=True):
    url: str = Field(unique=True, index=True)
    title: Optional[str] = Field(default=None, index=True)
    content_type: Optional[str] = Field(default='fragment') # e.g., 'article', 'video', 'audio', 'image'
    source: Optional[str] = Field(default=None, index=True)
    insertion_date: str = Field(default_factory=lambda: datetime.utcnow().isoformat(), index=True)
    content_language: Optional[str] = Field(default=None, index=True)
    author: Optional[str] = Field(default=None, index=True)
    publication_date: Optional[str] = Field(default=None, index=True)
    version: int = Field(default=1)
    is_active: bool = Field(default=True)
    summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    meta_summary: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Primary text content for articles and text-based content
    text_content: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Embeddings at the content level
    embeddings: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))

    # Relationships
    media_details: Optional["MediaDetails"] = Relationship(
        back_populates="content", sa_relationship_kwargs={"uselist": False}
    )
    entities: List["Entity"] = Relationship(back_populates="contents", link_model=ContentEntity)
    tags: List["Tag"] = Relationship(back_populates="contents", link_model=ContentTag)
    chunks: List["ContentChunk"] = Relationship(back_populates="content")

    topics: List["Topic"] = Relationship(back_populates="contents", link_model=ContentTopic)

    xclassifications: List["XClassification"] = Relationship(back_populates="content")

    evaluation: Optional["ContentEvaluation"] = Relationship(
        back_populates="content", sa_relationship_kwargs={"uselist": False}
    )


class MediaDetails(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    content_id: uuid.UUID = Field(foreign_key="content.id")
    duration: Optional[float] = Field(default=None)  # For audio and video
    transcribed_text: Optional[str] = Field(default=None, sa_column=Column(Text))  # For audio and video
    captions: Optional[str] = Field(default=None, sa_column=Column(Text))  # For videos
    top_image: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Relationships
    content: Content = Relationship(back_populates="media_details")
    video_frames: Optional[List["VideoFrame"]] = Relationship(back_populates="media_details")
    images: Optional[List["Image"]] = Relationship(back_populates="media_details")

class VideoFrame(SQLModel, table=True):
    media_details_id: uuid.UUID = Field(foreign_key="mediadetails.id", primary_key=True)
    frame_number: int = Field(primary_key=True)
    frame_url: str = Field(unique=True, index=True)
    timestamp: float = Field(index=True)
    embeddings: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))

    # Relationships
    media_details: MediaDetails = Relationship(back_populates="video_frames")

class Image(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    media_details_id: uuid.UUID = Field(foreign_key="mediadetails.id", index=True)
    image_url: str = Field(unique=True, index=True)
    caption: Optional[str] = Field(default=None)
    embeddings: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))

    # Relationships
    media_details: MediaDetails = Relationship(back_populates="images")

class ContentChunk(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    content_id: uuid.UUID = Field(foreign_key="content.id", index=True)
    chunk_number: int = Field(index=True)
    text: str = Field(sa_column=Column(Text))
    embeddings: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))

    # Relationships
    content: Content = Relationship(back_populates="chunks")

class Entity(BaseModel, table=True):
    name: str = Field(index=True)
    entity_type: str = Field(index=True)  # e.g., 'Person', 'Organization', 'Location', etc.

    # Relationships
    contents: List[Content] = Relationship(back_populates="entities", link_model=ContentEntity)
    locations: List["Location"] = Relationship(back_populates="entities", link_model=EntityLocation)

class Location(BaseModel, table=True):
    name: str = Field(index=True)
    location_type: Optional[str] = Field(default=None, index=True)  # e.g., 'city', 'state', 'country'
    coordinates: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(2)))
    weight: float = Field(default=0.0)

    entities: List[Entity] = Relationship(back_populates="locations", link_model=EntityLocation)

class Tag(BaseModel, table=True):
    name: str = Field(unique=True, index=True)
    contents: List[Content] = Relationship(back_populates="tags", link_model=ContentTag)

class ClassificationType(str, Enum):
    STRING = 'str'
    INTEGER = 'int'
    LIST_STRING = 'List[str]'
    FLOAT = 'float'
    BOOLEAN = 'bool'

class ClassificationDimension(BaseModel, table=True):
    name: str = Field(index=True, unique=True)
    type: ClassificationType = Field(index=True)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))

    # Relationships
    xclassifications: List["XClassification"] = Relationship(back_populates="dimension")

class XClassification(SQLModel, table=True):
    content_id: uuid.UUID = Field(foreign_key="content.id", primary_key=True)
    dimension_id: uuid.UUID = Field(foreign_key="classificationdimension.id", primary_key=True)
    value: Union[str, int, List[str]] = Field(sa_column=Column(JSONB))

    # Relationships
    content: "Content" = Relationship(back_populates="xclassifications")
    dimension: "ClassificationDimension" = Relationship(back_populates="xclassifications")

class Topic(BaseModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    keywords: Optional[List[str]] = Field(default_factory=list, sa_column=Column(ARRAY(Text)))
    top_entities: Optional[List[str]] = Field(default_factory=list, sa_column=Column(ARRAY(Text)))
    geo_reach: Optional[List[str]] = Field(default_factory=list, sa_column=Column(ARRAY(Text)))
    content_count: int = Field(default=0, index=True)

    # Relationships
    contents: List["Content"] = Relationship(back_populates="topics", link_model=ContentTopic)

# New Model
class ContentEvaluation(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    content_id: uuid.UUID = Field(foreign_key="content.id")

    # Thematic Locations
    thematic_locations: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(Text)))

    # Rhetoric
    rhetoric: Optional[str] = Field(default="neutral")
    
    # Impact Analysis
    sociocultural_interest: Optional[int] = Field(None, ge=0, le=10)
    global_political_impact: Optional[int] = Field(None, ge=0, le=10)
    regional_political_impact: Optional[int] = Field(None, ge=0, le=10)
    global_economic_impact: Optional[int] = Field(None, ge=0, le=10)
    regional_economic_impact: Optional[int] = Field(None, ge=0, le=10)
    
    # Event Classification
    event_type: Optional[str] = Field(default=None)
    event_subtype: Optional[str] = Field(default=None)
    
    # Keywords and Categories
    categories: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(Text)))

    # Relationships
    content: Content = Relationship(back_populates="evaluation")