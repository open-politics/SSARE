from .client_base import BaseClient
from typing import List, Optional
from pydantic import BaseModel
import json

class Economic(BaseClient):
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        super().__init__(mode, api_key=api_key, timeout=timeout, service_name="service-scraper", port=8081)

    def indicators(self, location: str = "Germany", pretty: Optional[bool] = False) -> dict:
        location = location.lower()
        endpoint = f"/economic/{location}"
        return self.get(endpoint)