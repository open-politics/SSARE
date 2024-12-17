from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ValidationError, field_validator
import json

# Initial Filter using Literal
class ContentRelevance(BaseModel):
    """
    Assess whether the given headline represents a substantial article or merely unwanted scraped material.
    If the headline consists solely of a single keyword such as "Technology," "Asia," "404 - Page not found," or "Data Privacy," it is likely deemed unwanted and should be classified as "Other."
    """
    type: Literal["Content", "Other"]

# Comprehensive Evaluation using Literal
class ContentEvaluation(BaseModel):
    """
    Evaluate content for political analysis across dimensions: locations, rhetoric, impact, events, and categories.

    1. Locations: Identify and thematic locations.
    2. Rhetoric: Determine tone: "neutral," "emotional," "argumentative," "optimistic," "pessimistic."
    3. Impact: Assess sociocultural, global/regional political, and economic impacts on a scale of 0-10.
       - Sociocultural: Cultural and societal relevance.
       - Political: Implications on global and regional politics.
       - Economic: Implications on global and regional economies.
    4. Events: Classify event type and provide specific subtype if applicable. Choose from:
    5. Categories: List content/ news categories.
    """

    thematic_locations: Optional[List[str]] = Field(None)

    # Impact Analysis
    sociocultural_interest: Optional[int] = Field(None, ge=0, le=10)
    global_political_impact: Optional[int] = Field(None, ge=0, le=10)
    regional_political_impact: Optional[int] = Field(None, ge=0, le=10)
    global_economic_impact: Optional[int] = Field(None, ge=0, le=10)
    regional_economic_impact: Optional[int] = Field(None, ge=0, le=10)

    # Event Classification
    event_type: Optional[Literal[
        "Protests", "Elections", "Politics", "Economic", "Legal", 
        "Social", "Crisis", "War", "Peace", "Diplomacy", 
        "Technology", "Science", "Culture", "Sports", "Other"
    ]] = Field(None)
    event_subtype: Optional[str] = Field(None)

    categories: Optional[List[str]] = Field(None)

    # Validators
    @field_validator(
        'sociocultural_interest', 
        'global_political_impact', 
        'regional_political_impact', 
        'global_economic_impact', 
        'regional_economic_impact', 
        mode='before'
    )
    def score_must_be_within_range(cls, v, info):
        if not isinstance(v, int):
            raise ValueError(f"{info.field_name} must be an integer.")
        if not 0 <= v <= 10:
            raise ValueError(f"{info.field_name} must be between 0 and 10.")
        return v

    @field_validator('categories', mode='before')
    def validate_lists(cls, v, info):
        if v is None:
            return v

        # If the input is a string that looks like a list, try to parse it
        if isinstance(v, str):
            try:
                v = json.loads(v.replace("'", '"'))
            except json.JSONDecodeError:
                raise ValueError(f"{info.field_name} must be a list of strings.")

        if not isinstance(v, list):
            raise ValueError(f"{info.field_name} must be a list of strings.")

        # Ensure all elements are strings
        if not all(isinstance(item, str) for item in v):
            raise ValueError(f"All items in {info.field_name} must be strings.")

        return v

