from typing import Dict
from .client_base import BaseClient

class Embeddings(BaseClient):
    """
    Client to interact with the Embeddings API endpoints.
    """
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        super().__init__(mode, api_key=api_key, timeout=timeout, service_name="embeddings-service", port=420)
    
    def __call__(self, *args, **kwargs):
        return self.get_embeddings(*args, **kwargs)
    
    def get_embeddings(self, text: str) -> dict:
        endpoint = f"/generate_query_embeddings"
        params = {"query": text}
        response = self.get(endpoint, params)
        embeddings = response.get("embeddings", [])
        return embeddings


