from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class ArticleBase(BaseModel):
    url: str = Field(...)
    headline: str = Field(...)
    paragraphs: List[str] = Field(...)
    source: Optional[str] = None  # Extendable field for the article's source
    embeddings: Optional[List[float]] = None

    class Config:
        orm_mode = True