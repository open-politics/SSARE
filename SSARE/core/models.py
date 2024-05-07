from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, ARRAY, Float, Integer
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class ArticlePydantic(BaseModel):
    url: str = Field(...)
    headline: Optional[str] = None
    paragraphs: Optional[str] = None
    source: Optional[str] = None
    embeddings: Optional[List[float]] = None

    class Config:
        orm_mode = True

class ArticleBase(Base):
    __tablename__ = "articles"
    url = Column(String, primary_key=True)  # Url & Unique Identifier
    headline = Column(String, nullable=True)  # Headline 
    paragraphs = Column(String, nullable=True)  # Text
    source = Column(String, nullable=True)  # 'cnn'
    embeddings = Column(ARRAY(Float), nullable=True)  # [3223, 2342, ..]
    entities = Column(JSONB, nullable=True)  # JSONB for storing entities
    geocodes = Column(ARRAY(JSONB), nullable=True)  # JSON objects for geocodes
    embeddings_created = Column(Integer, default=0)  # Flag
    stored_in_qdrant = Column(Integer, default=0)  # Flag 
    entities_extracted = Column(Integer, default=0)  # Flag
    geocoding_created = Column(Integer, default=0)  # Flag