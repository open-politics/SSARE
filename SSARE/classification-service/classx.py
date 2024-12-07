from typing import List, Union
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import create_model, BaseModel, Field
from enum import Enum
from core.models import ClassificationDimension, ClassificationType
from openai import OpenAI
import instructor
import google.generativeai as genai
import os


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

def get_llm_client():
    """Get the LLM client based on environment settings."""
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    return instructor.from_gemini(
        client=genai.GenerativeModel(
            model_name="models/gemini-1.5-flash-latest",
        ),
        mode=instructor.Mode.GEMINI_JSON,
    )

def classify_with_model(content, llm_model, response_model, system_prompt, user_content):
    """Classify content using the specified model and return the response."""
    client = get_llm_client()
    response = client.chat.completions.create(
        # model=llm_model, not if using gemini
        response_model=response_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    return response
