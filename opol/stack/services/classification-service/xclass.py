from typing import Any, List, Optional, Type
from pydantic import BaseModel, Field, create_model
from enum import Enum
import os
import google.generativeai as genai
import instructor
import json

from core.utils import logger
from core.models import ClassificationDimension
from classification_models import ContentEvaluation, ContentRelevance

class XClass:
    """
    Comprehensive service for dynamic classifications.
    Encapsulates the functionalities of DynamicClassifier and ClassificationWrapper.
    """

    def __init__(self, client_instance=None):
        """
        Initialize the ClassificationService with a client.
        """
        if client_instance:
            self.client = client_instance
        else:
            # Configure LiteLLM
            my_proxy_api_key = "sk-1234"
            my_proxy_base_url = "http://litellm:4000"
    
            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            self.client = instructor.from_gemini(
                client=genai.GenerativeModel(
                    model_name="models/gemini-1.5-flash-latest", 
                ),
                mode=instructor.Mode.GEMINI_JSON,
            )

    def map_python_type_to_dim_type(self, python_type: Any) -> str:
        """
        Map Python types to classification dimension types.
        """
        type_mapping = {
            bool: "binary",
            str: "string",
            int: "integer",
            float: "numeric",
            List[str]: "list_string"
        }
        return type_mapping.get(python_type, "string")

    def create_dynamic_classification_model(self, dimensions: List[ClassificationDimension]) -> Type[BaseModel]:
        """
        Create a dynamic Pydantic model for classifications based on provided dimensions.
        """
        fields = {}
        for dim in dimensions:
            dim_type = dim.type.lower()
            if dim_type == 'binary':
                field_type = (bool, Field(description=dim.description))
            elif dim_type == 'string':
                field_type = (str, Field(description=dim.description))
            elif dim_type == 'integer':
                field_type = (int, Field(description=dim.description))
            elif dim_type == 'numeric':
                field_type = (float, Field(description=dim.description))
            elif dim_type == 'list_string':
                field_type = (List[str], Field(description=dim.description))
            else:
                logger.warning(f"Unhandled dimension type: {dim_type}")
                continue  # Skip unhandled types
            fields[dim.name] = field_type

        DynamicClassificationModel = create_model('DynamicClassificationModel', **fields)
        return DynamicClassificationModel

    def create_dynamic_classification_model_from_model(self, response_model: Type[BaseModel]) -> Type[BaseModel]:
        """
        Create a dynamic classification model based on a predefined Pydantic response model.
        """
        dimensions = []
        for field_name, field in response_model.__fields__.items():
            dim_type = self.map_python_type_to_dim_type(field.type_)
            dim = ClassificationDimension(
                name=field_name, 
                type=dim_type, 
                description=field.field_info.description or ""
            )
            dimensions.append(dim)
        
        return self.create_dynamic_classification_model(dimensions)
    
    def build_system_prompt(self, dimensions: List[ClassificationDimension]) -> str:
        """
        Build the system prompt for the classification model based on dimensions.
        """
        prompt = "You are an AI assistant that analyzes content and provides classifications based on specified dimensions.\n\n"
        prompt += "Please provide the following classifications:\n"
        for dim in dimensions:
            prompt += f"- {dim.name}: {dim.description}\n"
        return prompt

    def build_system_prompt_from_model(self, response_model: Type[BaseModel]) -> str:
        """
        Build the system prompt based on a predefined Pydantic response model.
        """
        dimensions = []
        for field_name, field in response_model.__fields__.items():
            dim_type = self.map_python_type_to_dim_type(field.type_)
            dim = ClassificationDimension(
                name=field_name,
                type=dim_type,
                description=field.field_info.description or ""
            )
            dimensions.append(dim)
        
        return self.build_system_prompt(dimensions)

    def classify(
        self, 
        response_model: Type[BaseModel], 
        text: str, 
        dimensions: Optional[List[ClassificationDimension]] = None
    ) -> BaseModel:
        """
        General classification method.
        """
        try:
            if dimensions:
                DynamicClassificationModel = self.create_dynamic_classification_model(dimensions)
                system_prompt = self.build_system_prompt(dimensions)
            else:
                # Infer dimensions from the response_model
                DynamicClassificationModel = self.create_dynamic_classification_model_from_model(response_model)
                system_prompt = self.build_system_prompt_from_model(response_model)
            
            classification_result = self.classify_with_model(
                response_model=DynamicClassificationModel,
                system_prompt=system_prompt,
                user_content=text
            )
            return classification_result
        except Exception as e:
            logger.error(f"ClassificationService error: {e}")
            raise

    def classify_custom(
        self, 
        response_model: Type[BaseModel], 
        text: str
    ) -> BaseModel:
        """
        Convenience method to classify without specifying dimensions.
        """
        return self.classify(response_model=response_model, text=text)
    
    def classify_with_model(
        self,
        response_model: Type[BaseModel],
        system_prompt: str,
        user_content: str
    ) -> BaseModel:
        """
        Classify content using the LLM model with the provided system prompt and user content.
        """
        try:
            response = self.client.chat.completions.create(
                response_model=response_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
            )
            return response
        except Exception as e:
            logger.error(f"Error during classification with model: {e}")
            raise