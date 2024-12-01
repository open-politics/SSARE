from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel
from fastapi import Query

class SearchType(str, Enum):
    TEXT = "text"
    SEMANTIC = "semantic"
    STRUCTURED = "structured" 
    LOCATION = "location"