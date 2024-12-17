from .client_base import BaseClient

class Entities(BaseClient):
    """
    Client to interact with the Entities API endpoints.
    """
    def __init__(self, mode: str, base_url: str, api_key: str = None):
        super().__init__(mode, base_url, api_key)
    
    def __call__(self, *args, **kwargs):
        return self.get_entities(*args, **kwargs)

    def get_entities(self, location_name: str, skip: int = 0, limit: int = 50) -> dict:
        endpoint = f"postgres-service/routes/search/location_entities/{location_name}"
        params = {"skip": skip, "limit": limit}
        return self.get(endpoint, params)
    
    def by_id(self, entity_id: str) -> dict:
        endpoint = f"postgres-service/routes/search/entity/{entity_id}"
        return self.get(endpoint)

    def by_location(self, location_name: str, skip: int = 0, limit: int = 50) -> dict:
        endpoint = f"postgres-service/routes/search/location_entities/{location_name}"
        params = {"skip": skip, "limit": limit}
        return self.get(endpoint, params)