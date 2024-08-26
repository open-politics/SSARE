from typing import List, Optional
from datetime import datetime
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, Integer, Text, ARRAY
from pgvector.sqlalchemy import Vector
import uuid

class BaseModel(SQLModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

class BaseDoc(SQLModel):
    url: str = Field(unique=True, primary_key=True)
    headline: str = None
    paragraphs: str = None

class ArticleEntity(SQLModel, table=True):
    article_id: uuid.UUID = Field(foreign_key="article.id", primary_key=True)
    entity_id: uuid.UUID = Field(foreign_key="entity.id", primary_key=True)
    frequency: int = Field(default=1)

class ArticleTag(SQLModel, table=True):
    article_id: uuid.UUID = Field(foreign_key="article.id", primary_key=True)
    tag_id: uuid.UUID = Field(foreign_key="tag.id", primary_key=True)

class NewsArticleClassification(BaseModel, table=True):
    article_id: uuid.UUID = Field(foreign_key="article.id", primary_key=True)
    title: str
    news_category: str
    secondary_categories: List[str] = Field(sa_column=Column(ARRAY(Text)))
    keywords: List[str] = Field(sa_column=Column(ARRAY(Text)))
    geopolitical_relevance: int
    legislative_influence_score: int
    international_relevance_score: int
    democratic_process_implications_score: int
    general_interest_score: int
    spam_score: int
    clickbait_score: int
    fake_news_score: int
    satire_score: int

    article: "Article" = Relationship(back_populates="classification")

class EntityLocation(SQLModel, table=True):
    entity_id: uuid.UUID = Field(foreign_key="entity.id", primary_key=True)
    location_id: uuid.UUID = Field(foreign_key="location.id", primary_key=True)

class Article(BaseModel, table=True):
    url: str = Field(unique=True, index=True)
    headline: str = Field(index=True)
    paragraphs: str = Field(sa_column=Column(Text))
    source: str = Field(index=True)
    insertion_date: Optional[datetime] = Field(default=None, index=True)
    embeddings: Optional[List[float]] = Field(default=None, sa_column=Column(Vector(768)))

    entities: Optional[List["Entity"]] = Relationship(back_populates="articles", link_model=ArticleEntity)
    classification: Optional[NewsArticleClassification] = Relationship(back_populates="article")
    tags: Optional[List["Tag"]] = Relationship(back_populates="articles", link_model=ArticleTag)


class Articles(SQLModel):
    articles: List[Article]

    
class Entity(BaseModel, table=True):
    name: str = Field(index=True)
    entity_type: str = Field(index=True)

    articles: List[Article] = Relationship(back_populates="entities", link_model=ArticleEntity)
    locations: List["Location"] = Relationship(back_populates="entities", link_model=EntityLocation)

class Location(BaseModel, table=True):
    name: str = Field(index=True)
    type: str = Field(index=True)  # e.g., city, state, country
    coordinates: List[float] = Field(sa_column=Column(Vector(2)))
    weight: float = Field(default=0.0)

    entities: List[Entity] = Relationship(back_populates="locations", link_model=EntityLocation)

class Tag(BaseModel, table=True):
    name: str = Field(unique=True, index=True)

    articles: List[Article] = Relationship(back_populates="tags", link_model=ArticleTag)

class ArticleTags(SQLModel):
    tags: List[Tag]