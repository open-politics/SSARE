from enum import Enum
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ValidationError, field_validator, ConfigDict
import json


class EventType(Enum):
    PROTESTS = "Protests"
    ELECTIONS = "Elections"
    ECONOMIC = "Economic"
    LEGAL = "Legal"
    SOCIAL = "Social"
    CRISIS = "Crisis"
    WAR = "War"
    PEACE = "Peace"
    DIPLOMACY = "Diplomacy"
    TECHNOLOGY = "Technology"
    SCIENCE = "Science"
    CULTURE = "Culture"
    SPORTS = "Sports"
    OTHER = "Other"


class RhetoricType(Enum):
    AGGRESSIVE = "Aggressive"
    PERSUASIVE = "Persuasive"
    INFORMATIVE = "Informative"
    EMOTIONAL = "Emotional"
    NEUTRAL = "Neutral"
    OTHER = "Other"


class ContentEvaluation(BaseModel):
    """Comprehensive evaluation of content for political text-as-data analysis."""

    # Rhetorical Analysis
    rhetoric: Optional[Literal["Aggressive", "Persuasive", "Informative", "Emotional", "Neutral", "Other"]] = None
    persuasive_elements: Optional[List[str]] = Field(
        None, description="List of persuasive elements used in the article."
    )
    emotional_tone: Optional[str] = Field(
        None, description="Description of the emotional tone conveyed in the article."
    )
    
    # Impact Analysis
    general_interest_score: Optional[int] = Field(None, ge=0, le=10, description="Score representing general public interest.")
    global_political_impact_score: Optional[int] = Field(None, ge=0, le=10, description="Score representing the global impact of the content.")
    regional_political_impact_score: Optional[int] = Field(None, ge=0, le=10, description="Score representing the regional impact of the content.")
    global_economic_impact_score: Optional[int] = Field(None, ge=0, le=10, description="Score representing the economic impact of the content.")
    regional_economic_impact_score: Optional[int] = Field(None, ge=0, le=10, description="Score representing the regional economic impact of the content.")
    
    # Event Classification
    event_type: Optional[Literal["Protests", "Elections", "Economic", "Legal", "Social", "Crisis", "War", "Peace", "Diplomacy", "Technology", "Science", "Culture", "Sports", "Other"]] = None
    event_subtype: Optional[str] = Field(None, description="Subtype or specific category of the event.")
    
    
    # Keywords and Categories
    keywords: Optional[List[str]] = Field(None, description="List of keywords associated with the article.")
    categories: Optional[List[str]] = Field(None, description="List of categories the article belongs to.")
    
    # Validators
    @field_validator('global_political_impact_score', 'regional_political_impact_score', 'global_economic_impact_score', 'regional_economic_impact_score',
                     'general_interest_score', mode='before')
    def score_must_be_within_range(cls, v, info):
        if not isinstance(v, int):
            raise ValueError(f"{info.field_name} must be an integer.")
        if not 0 <= v <= 10:
            raise ValueError(f"{info.field_name} must be between 0 and 10.")
        return v
    
    @field_validator('persuasive_elements', mode='before')
    def validate_persuasive_elements(cls, v):
        if v is not None and not isinstance(v, list):
            raise ValueError("persuasive_elements must be a list of strings.")
        return v
    
    @field_validator('keywords', 'categories', mode='before')
    def validate_lists(cls, v, info):
        if not isinstance(v, list):
            raise ValueError(f"{info.field_name} must be a list of strings.")
        return v

    # Override the default JSON serialization method
    def to_json(self):
        return json.dumps(self.dict(), default=lambda o: o.value if isinstance(o, Enum) else o)

