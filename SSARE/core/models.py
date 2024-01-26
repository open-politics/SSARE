from pydantic import BaseModel, Field
from typing import List, Optional

class ArticleBase(BaseModel):
    url: str = Field(...)
    headline: str = Field(...)
    paragraphs: List[str] = Field(...)
    source: Optional[str] = None
    embeddings: Optional[List[float]] = None

    class Config:
        orm_mode = True
