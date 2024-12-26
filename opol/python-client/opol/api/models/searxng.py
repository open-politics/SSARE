from typing import List, Optional
from pydantic import BaseModel

class SearXngResults(BaseModel):
        url: str
        title: str
        content : Optional[str] = None
        publishedDate : Optional[str] = None
        thumbnail : Optional[str] = None
        engine : Optional[str] = None
        parsed_url : Optional[List[str]] = None
        template : Optional[str] = None
        engines : Optional[List[str]] = None
        positions : Optional[List[int]] = None
        score : Optional[float] = None
        category : Optional[str] = None

class SearXngResponse(BaseModel):
    query : str
    results : List[SearXngResults]