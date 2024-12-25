from typing import Any, Dict, Type, Union, List, Optional, get_origin, get_args
from pydantic import BaseModel, create_model, Field
import inspect

import google.generativeai as genai
import instructor


# A small helper map to parse string -> Python type
# Expand as needed (e.g. float, bool, etc.).
BUILTIN_TYPES: Dict[str, Any] = {
    "int": int,
    "str": str,
    "List[str]": List[str],
    "bool": bool,
}


class FastClass:    
    """
    A convenience class that wraps Google Generative AI with 'instructor' in JSON mode.
    It can accept either a string-based type definition or a full Pydantic model.
    """

    def __init__(self, model_name: str = "gemini-1.5-flash"):
        # In practice, configure your Google Generative AI model here
        self.client = instructor.from_gemini(
            client=genai.GenerativeModel(model_name=model_name),
            mode=instructor.Mode.GEMINI_JSON,
        )

    def infer(
        self,
        type_or_model: Union[str, Type[BaseModel]],
        user_input: str,
        prompt: Optional[str] = None,
    ) -> Any:
        """
        Dynamically infer the result from the LLM.

        :param type_or_model: Either a string that indicates the desired Python type
                            (e.g. "int", "List[str]", etc.) or a Pydantic model class.
        :param prompt: The high-level prompt/instructions to be sent to the LLM.
        :param user_input: The user-provided text or context on which we want to run inference.
        :return: Parsed response, either a simple Python type (if type_or_model is a string)
                or an instance of the Pydantic model (if type_or_model is a BaseModel).

        Mapping pydantic types:
        BUILTIN_TYPES: Dict[str, Any] = {
            "int": int,
            "str": str,
            "List[str]": List[str],
            "bool": bool,
        }
        """
        # 1. Build the final prompt from hierarchy: prompt -> model docstring -> field docstrings
        combined_prompt = self._build_prompt(type_or_model, prompt, user_input)

        # 2. Determine the appropriate "response_model" for the instructor client.
        #    If it’s a string-based type, we create a dynamic single-field model on the fly.
        if isinstance(type_or_model, str):
            # create a single-field Pydantic model
            dynamic_model = self._create_single_field_model(type_or_model)
            response_model = dynamic_model
        else:
            # type_or_model is already a Pydantic model class
            response_model = type_or_model

        # 3. Call the LLM with the combined prompt, parse result as JSON → Pydantic
        llm_response = self.client.messages.create(
            messages=[
                {
                    "role": "user",
                    "content": combined_prompt,
                }
            ],
            response_model=response_model,
        )

        # 4. If we used a single-field dynamic model, return just that field’s value.
        if isinstance(type_or_model, str):
            field_name = list(llm_response.model_fields.keys())[0]
            return getattr(llm_response, field_name)
        else:
            # If it's a Pydantic model, return the entire model instance
            return llm_response

    def _build_prompt(
        self,
        type_or_model: Union[str, Type[BaseModel]],
        prompt: str,
        user_input: str,
    ) -> str:
        """
        Build a single textual prompt with the hierarchy:
        1) The user prompt
        2) Model docstring (if a BaseModel)
        3) Field annotations (if a BaseModel)
        """
        lines = []
        # The main "prompt" from the user
        lines.append(prompt.strip()) if prompt else None

        # If we have a BaseModel, we can incorporate its docstring + field docstrings
        if not isinstance(type_or_model, str):
            # Add model docstring
            model_doc = inspect.getdoc(type_or_model) or ""
            if model_doc:
                lines.append(f"\nMODEL DESCRIPTION:\n{model_doc}")

            # Add field-level docstrings from pydantic Fields
            for field_name, field_def in type_or_model.model_fields.items():
                default_val = field_def.default
                annotation = field_def.annotation

                # Field may have a Field(...) with description
                # For instance:
                #   field_name: str = Field(..., description="Explain me")
                #
                # We retrieve that from the metadata:
                if field_def.description:
                    lines.append(
                        f"\nFIELD '{field_name}' DESCRIPTION: {field_def.description}"
                    )

        # Finally, add the user input
        lines.append(f"\nUSER INPUT:\n{user_input}")

        return "\n".join(lines).strip()

    def _create_single_field_model(self, type_str: str) -> Type[BaseModel]:
        """
        Dynamically create a single-field model from a string type.
        E.g. type_str = "int", "List[str]", "bool", ...
        """
        if type_str not in BUILTIN_TYPES:
            raise ValueError(
                f"Type '{type_str}' not recognized. "
                f"Please add it to the BUILTIN_TYPES dict."
            )

        field_type = BUILTIN_TYPES[type_str]
        dynamic_model = create_model(
            "DynamicSingleFieldModel",
            __base__=BaseModel,
            single_field=(field_type, Field(..., description=f"A {type_str} value.")),
        )
        return dynamic_model

