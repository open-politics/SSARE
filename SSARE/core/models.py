from pydantic import BaseModel, Field
from typing import List, Optional

class ArticleBase(BaseModel):
    url: str = Field(...)
    headline: str = Field(...)
    paragraphs: str = Field(...)
    source: Optional[str] = None
    embeddings: Optional[List[float]] = None

    class Config:
        orm_mode = True

class ArticleModel(BaseModel):
    url: str = Field(..., description="The URL of the article")
    headline: str = Field(..., description="The headline of the article")
    paragraphs: str = Field(..., description="The paragraphs of the article")
    source: Optional[str] = Field(None, description="The source of the article")
    embeddings: Optional[List[float]] = Field(None, description="The vector embeddings of the article's content")
    embeddings_created: Optional[bool] = Field(False, description="Flag to indicate if embeddings are created")
    isStored_in_qdrant: Optional[bool] = Field(False, description="Flag to indicate if the article is stored in Qdrant")

    class Config:
        orm_mode = True
        schema_extra = {
            "example": {
                "url": "https://example-news.com/article1",
                "headline": "Breaking News: Example Event Occurs",
                "paragraphs": "Example paragraph 1. Example paragraph 2. Example paragraph 3",
                "source": "Example News",
                "embeddings": [0.01, 0.02, ..., 0.05],
                "embeddings_created": True,
                "isStored_in_qdrant": True
            }
        }

