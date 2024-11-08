from typing import List, Union
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import create_model, BaseModel, Field
from enum import Enum
from core.models import ClassificationDimension, ClassificationType


# Function to create dynamic pydantic model for classifications
def create_dynamic_classification_model(dimensions: List[ClassificationDimension]) -> BaseModel:
    fields = {}
    for dim in dimensions:
        if dim.type == ClassificationType.STRING:
            field_type = (str, Field(description=dim.description))
        elif dim.type == ClassificationType.INTEGER:
            field_type = (int, Field(description=dim.description))
        elif dim.type == ClassificationType.LIST_STRING:
            field_type = (List[str], Field(description=dim.description))
        else:
            continue  # Skip unhandled types
        fields[dim.name] = field_type

    DynamicClassificationModel = create_model('DynamicClassificationModel', **fields)
    return DynamicClassificationModel

# Function to build the system prompt
def build_system_prompt(dimensions: List[ClassificationDimension]) -> str:
    prompt = "You are an AI assistant that analyzes articles and provides classifications based on specified dimensions.\n\n"
    prompt += "Please provide the following classifications:\n"
    for dim in dimensions:
        prompt += f"- {dim.name}: {dim.description}\n"
    return prompt