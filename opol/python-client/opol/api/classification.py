from typing import Dict
from .client_base import BaseClient

class Classification(BaseClient):
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        super().__init__(mode, 
                         api_key=api_key, 
                         timeout=timeout, 
                         service_name="classification-service", 
                         port=3691)

    def get_classification(self, text: str) -> Dict:
        # Just the endpoint name
        endpoint = "classify"
        return self.post(endpoint, {"text": text})
