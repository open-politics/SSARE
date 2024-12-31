from typing import Any, Type, Union
from .client_base import BaseClient
from pydantic import BaseModel
from .fastclass import FastClass

class Classification(BaseClient):
    def __init__(
            self, 
            mode: str, 
            api_key: str = None, 
            timeout: int = 60, 
            provider: str = "Google", 
            model_name: str = "models/gemini-1.5-flash-latest", 
            llm_api_key: str = None):
        
        super().__init__(
            mode,
            api_key=api_key,
            timeout=timeout,
            service_name="service-classification",
            port=5688
        )
        
        self.fastclass = FastClass(provider=provider, model_name=model_name, llm_api_key=llm_api_key)
        
    def classify(
        self,
        response_type: Union[str, Type[BaseModel]],
        prompt: str,
        input_text: str
    ) -> Any:
        """
        Unified classify method that integrates directly with FastClass.
        """
        return self.fastclass.infer(response_type, input_text, prompt)
