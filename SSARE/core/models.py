from typing import List, Optional
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Float
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from pgvector.sqlalchemy import Vector

class Entity(SQLModel):
    tag: str
    text: str

class Geocode(SQLModel):
    location: str
    coordinates: List[float]

class Article(SQLModel, table=True):
    url: str = Field(primary_key=True)
    headline: Optional[str] = None
    paragraphs: str
    source: Optional[str] = None
    embeddings: Optional[List[float]] = Field(sa_column=Column(Vector(768)))
    entities: Optional[List[Entity]] = Field(sa_column=Column(JSONB))
    geocodes: Optional[List[Geocode]] = Field(sa_column=Column(JSONB))
    tags: List[str] = Field(default_factory=list, sa_column=Column(ARRAY(Float)))
    embeddings_created: int = Field(default=0)
    pgvectors_available: int = Field(default=0)  
    entities_extracted: int = Field(default=0)
    geocoding_created: int = Field(default=0)

    class Config:
        arbitrary_types_allowed = True
