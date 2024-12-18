from typing import List, Union, Optional, Type
from pydantic import create_model, BaseModel, Field
from enum import Enum
from openai import OpenAI
import instructor

from core.models import ClassificationType

# Function to create dynamic Pydantic model for classifications
def create_dynamic_classification_model(dimensions: List[BaseModel]) -> BaseModel:
    fields = {}
    for dim in dimensions:
        if dim.type.lower() == 'string':
            field_type = (str, Field(description=dim.description))
        elif dim.type.lower() == 'integer':
            field_type = (int, Field(description=dim.description))
        elif dim.type.lower() == 'list_string':
            field_type = (List[str], Field(description=dim.description))
        else:
            continue  # Skip unhandled types
        fields[dim.name] = field_type

    DynamicClassificationModel = create_model('DynamicClassificationModel', **fields)
    return DynamicClassificationModel

# Function to build the system prompt
def build_system_prompt(dimensions: List[BaseModel]) -> str:
    prompt = "You are an AI assistant that analyzes entities and provides classifications based on specified dimensions.\n\n"
    prompt += "Please provide the following classifications:\n"
    for dim in dimensions:
        prompt += f"- {dim.name}: {dim.description}\n"
    return prompt

def classify_with_model(
    client,
    response_model: Type[BaseModel],
    system_prompt: str,
    user_content: str
) -> BaseModel:
    response = client.chat.completions.create(
        response_model=response_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
    )
    return response
