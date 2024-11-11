from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ValidationError, field_validator
import json

# Initial Filter using Literal
class ContentRelevance(BaseModel):
    """
    Determine if this is a proper article or unwanted material scraped along. 
    If the headline is a single Keyword like "Technology", "Asia", "404 - Page not found" or "Data Privacy", it is likely unwanted material and thus "Other",
    and should be classified as "Other".
    """
    type: Literal["Content", "Other"]

# Comprehensive Evaluation using Literal
class ContentEvaluation(BaseModel):
    """
    You are tasked with evaluating a piece of content for political text-as-data analysis. Your goal is to classify the content based on several criteria, including rhetorical analysis, impact analysis, event classification, and associated keywords and categories. Follow the guidelines below to complete the evaluation:
    Impact Analysis:
    Assess the sociocultural interest of the content on a scale from 0 to 10, where 0 indicates no interest and 10 indicates high interest.
    Evaluate the global political impact on a scale from 0 to 10.
    Evaluate the regional political impact on a scale from 0 to 10.
    Evaluate the global economic impact on a scale from 0 to 10.
    Evaluate the regional economic impact on a scale from 0 to 10.
    Event Classification:
    Identify the type of event the content is related to. Choose from the following options: Protests, Elections, Politics, Economic, Legal, Social, Crisis, War, Peace, Diplomacy, Technology, Science, Culture, Sports, Other.
    Specify a subtype or specific category of the event if applicable.
    4. Keywords and Categories:
    List relevant keywords associated with the content.
    Categorize the content into appropriate categories.
    Instructions:
    Ensure all numerical scores are integers between 0 and 10.
    Provide lists of keywords and categories as strings.
    If any field is not applicable, you may leave it as None.
    Example:
    Sociocultural Interest: 8
    Global Political Impact: 5
    Regional Political Impact: 7
    Global Economic Impact: 3
    Regional Economic Impact: 4
    Event Type: "Politics"
    Event Subtype: "Election Campaign"
    Keywords: ["election", "campaign", "politics"]
    Categories: ["Political Analysis", "Elections"]
    """
    
    # Impact Analysis
    sociocultural_interest: Optional[int] = Field(None, ge=0, le=10, description="Score representing general public interest.")
    global_political_impact: Optional[int] = Field(None, ge=0, le=10, description="Score representing the global impact of the content.")
    regional_political_impact: Optional[int] = Field(None, ge=0, le=10, description="Score representing the regional impact of the content.")
    global_economic_impact: Optional[int] = Field(None, ge=0, le=10, description="Score representing the economic impact of the content.")
    regional_economic_impact: Optional[int] = Field(None, ge=0, le=10, description="Score representing the regional economic impact of the content.")
    
    # Event Classification
    event_type: Optional[Literal["Protests", "Elections", "Politics", "Economic", "Legal", "Social", "Crisis", "War", "Peace", "Diplomacy", "Technology", "Science", "Culture", "Sports", "Other"]] = None
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
