# models.py

from __future__ import annotations
from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Text, ARRAY, String, Float, Integer, Boolean, JSON
from pgvector.sqlalchemy import Vector
import uuid

# Base model to add primary keys
class BaseModel(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

# Define link models first
class ContentEntity(SQLModel, table=True):
    __tablename__ = "content_entity"
    content_id: uuid.UUID = Field(foreign_key="content.id", primary_key=True)
    entity_id: uuid.UUID = Field(foreign_key="entity.id", primary_key=True)
    frequency: int = Field(default=1)

class ContentTag(SQLModel, table=True):
    __tablename__ = "content_tag"
    content_id: uuid.UUID = Field(foreign_key="content.id", primary_key=True)
    tag_id: uuid.UUID = Field(foreign_key="tag.id", primary_key=True)

class EntityLocation(SQLModel, table=True):
    __tablename__ = "entity_location"
    entity_id: uuid.UUID = Field(foreign_key="entity.id", primary_key=True)
    location_id: uuid.UUID = Field(foreign_key="location.id", primary_key=True)

class EntityRelationship(SQLModel, table=True):
    __tablename__ = "entity_relationship"
    left_entity_id: uuid.UUID = Field(foreign_key="entity.id", primary_key=True)
    right_entity_id: uuid.UUID = Field(foreign_key="entity.id", primary_key=True)
    relationship_type: str = Field(index=True)  # e.g., 'affiliated_with', 'parent_of', etc.

# Now define the rest of your models

class Content(BaseModel, table=True):
    __tablename__ = "content"
    url: str = Field(unique=True, index=True)
    title: Optional[str] = Field(default=None, index=True)
    content_type: str = Field(index=True)  # 'article', 'video', 'audio', 'image'
    source: Optional[str] = Field(default=None, index=True)
    insertion_date: datetime = Field(default_factory=datetime.utcnow, index=True)
    text_content: Optional[str] = Field(default=None, sa_column=Column(Text))  # For articles, transcriptions, captions
    embeddings: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))
    scrape_date: datetime = Field(default_factory=datetime.utcnow, index=True)
    content_language: Optional[str] = Field(default=None, index=True)
    author: Optional[str] = Field(default=None, index=True)
    publication_date: Optional[datetime] = Field(default=None, index=True)
    version: int = Field(default=1)
    is_active: bool = Field(default=True)

    # Relationships
    entities: List["Entity"] = Relationship(back_populates="contents", link_model=ContentEntity)
    classification: Optional["ContentClassification"] = Relationship(back_populates="content", sa_relationship_kwargs={"uselist": False})
    tags: List["Tag"] = Relationship(back_populates="contents", link_model=ContentTag)
    media_details: Optional["MediaDetails"] = Relationship(back_populates="content", sa_relationship_kwargs={"uselist": False})

class Entity(BaseModel, table=True):
    __tablename__ = "entity"
    name: str = Field(index=True)
    entity_type: str = Field(index=True)  # e.g., 'Person', 'Organization', 'Location', etc.
    attributes: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))

    # Relationships
    contents: List[Content] = Relationship(back_populates="entities", link_model=ContentEntity)

    # Relationships with other entities
    related_entities: List["Entity"] = Relationship(
        back_populates="related_to",
        link_model=EntityRelationship,
        sa_relationship_kwargs={
            "primaryjoin": "Entity.id==EntityRelationship.left_entity_id",
            "secondaryjoin": "Entity.id==EntityRelationship.right_entity_id"
        }
    )
    related_to: List["Entity"] = Relationship(
        back_populates="related_entities",
        link_model=EntityRelationship,
        sa_relationship_kwargs={
            "primaryjoin": "Entity.id==EntityRelationship.right_entity_id",
            "secondaryjoin": "Entity.id==EntityRelationship.left_entity_id"
        }
    )

    # Locations relationship
    locations: List["Location"] = Relationship(back_populates="entities", link_model=EntityLocation)

class Tag(BaseModel, table=True):
    __tablename__ = "tag"
    name: str = Field(unique=True, index=True)
    contents: List[Content] = Relationship(back_populates="tags", link_model=ContentTag)

class Location(BaseModel, table=True):
    __tablename__ = "location"
    name: str = Field(index=True)
    type: str = Field(index=True)  # e.g., 'city', 'state', 'country'
    coordinates: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(2)))
    weight: float = Field(default=0.0)

    entities: List[Entity] = Relationship(back_populates="locations", link_model=EntityLocation)

# Models with custom primary keys (inherit directly from SQLModel)
class MediaDetails(SQLModel, table=True):
    __tablename__ = "media_details"
    content_id: uuid.UUID = Field(foreign_key="content.id", primary_key=True)
    duration: Optional[float] = Field(default=None)  # For audio and video
    transcribed_text: Optional[str] = Field(default=None, sa_column=Column(Text))  # For audio and video

    # Relationships
    frame_data: List["VideoFrame"] = Relationship(back_populates="media_details")
    image_data: List["Image"] = Relationship(back_populates="media_details")
    content: Content = Relationship(back_populates="media_details", sa_relationship_kwargs={"uselist": False})

class ContentClassification(SQLModel, table=True):
    __tablename__ = "content_classification"
    content_id: uuid.UUID = Field(foreign_key="content.id", primary_key=True)
    category: str
    secondary_categories: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(String)))
    keywords: Optional[List[str]] = Field(default=None, sa_column=Column(ARRAY(String)))
    geopolitical_relevance: int
    legislative_influence_score: int
    international_relevance_score: int
    democratic_process_implications_score: int
    general_interest_score: int
    spam_score: int
    clickbait_score: int
    fake_news_score: int
    satire_score: int
    event_type: str  # e.g., 'Protests', 'Elections', etc.

    content: Content = Relationship(back_populates="classification", sa_relationship_kwargs={"uselist": False})

class VideoFrame(SQLModel, table=True):
    __tablename__ = "video_frame"
    media_details_id: uuid.UUID = Field(foreign_key="media_details.content_id", primary_key=True)
    frame_number: int = Field(primary_key=True)
    frame_url: str = Field(unique=True, index=True)
    timestamp: float = Field(index=True)
    embeddings: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))

    media_details: MediaDetails = Relationship(back_populates="frame_data", sa_relationship_kwargs={"uselist": False})

class Image(SQLModel, table=True):
    __tablename__ = "image"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    media_details_id: uuid.UUID = Field(foreign_key="media_details.content_id")
    image_url: str = Field(unique=True, index=True)
    caption: Optional[str] = Field(default=None)
    embeddings: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))

    media_details: MediaDetails = Relationship(back_populates="image_data", sa_relationship_kwargs={"uselist": False})
