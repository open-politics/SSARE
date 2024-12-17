from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ValidationError, field_validator
import json

## Initial Filter 
class ContentRelevance(Enum):
    type: Literal["Relevant", "Irrelevant", "Needs more context", "Needs more analysis"]



# Comprehensive Evaluation
class EventType(Enum):
    type: Literal["Protests", "Elections", "Economic", "Legal", "Social", "Crisis", "War", "Peace", "Diplomacy", "Technology", "Science", "Culture", "Sports", "Other"]

class RhetoricType(Enum):
    type: Literal["Aggressive", "Persuasive", "Informative", "Emotional", "Neutral", "Other"]

class ContentEvaluation(BaseModel):
    """Comprehensive evaluation of content for political text-as-data analysis."""
    # Rhetorical Analysis
    rhetoric: Optional[RhetoricType] = None
    
    # Impact Analysis
    sociocultural_interest: Optional[int] = Field(None, ge=0, le=10, description="Score representing general public interest.")
    global_political_impact: Optional[int] = Field(None, ge=0, le=10, description="Score representing the global impact of the content.")
    regional_political_impact: Optional[int] = Field(None, ge=0, le=10, description="Score representing the regional impact of the content.")
    global_economic_impact: Optional[int] = Field(None, ge=0, le=10, description="Score representing the economic impact of the content.")
    regional_economic_impact: Optional[int] = Field(None, ge=0, le=10, description="Score representing the regional economic impact of the content.")
    
    # Event Classification
    event_type: Optional[EventType] = None
    event_subtype: Optional[str] = Field(None, description="Subtype or specific category of the event.")
    
    # Keywords and Categories
    keywords: Optional[List[str]] = Field(None, description="List of keywords associated with the article.")
    categories: Optional[List[str]] = Field(None, description="List of categories the article belongs to.")
    
    # Validators
    @field_validator('sociocultural_interest', 'global_political_impact', 'regional_political_impact', 'global_economic_impact', 'regional_economic_impact', mode='before')
    def score_must_be_within_range(cls, v, info):
        if not isinstance(v, int):
            raise ValueError(f"{info.field_name} must be an integer.")
        if not 0 <= v <= 10:
            raise ValueError(f"{info.field_name} must be between 0 and 10.")
        return v
    
    @field_validator('keywords', 'categories', mode='before')
    def validate_lists(cls, v, info):
        if not isinstance(v, list):
            raise ValueError(f"{info.field_name} must be a list of strings.")
        return v

    # Override the default JSON serialization method
    def to_json(self):
        return json.dumps(self.dict(), default=lambda o: o.value if isinstance(o, Enum) else o)