from typing import Dict
from .client_base import BaseClient

class Entities(BaseClient):
    """
    Client to interact with the Entities API endpoints.
    """
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        super().__init__(mode, api_key=api_key, timeout=timeout, service_name="postgres-service", port=5434)
    
    def __call__(self, *args, **kwargs):
        return self.get_entities(*args, **kwargs)
    
    def get_entities(self, location_name: str, skip: int = 0, limit: int = 50) -> dict:
        endpoint = f"routes/search/location_entities/{location_name}"
        params = {"skip": skip, "limit": limit}
        return self.get(endpoint, params)
    
    def by_id(self, entity_id: str) -> dict:
        endpoint = f"routes/search/entity/{entity_id}"
        return self.get(endpoint)

    def by_location(self, location_name: str, skip: int = 0, limit: int = 50) -> dict:
        endpoint = f"routes/search/location_entities/{location_name}"
        params = {"skip": skip, "limit": limit}
        return self.get(endpoint, params)
