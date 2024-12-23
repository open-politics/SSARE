from .client_base import BaseClient
from typing import List, Optional
from pydantic import BaseModel
import json

class Scraping(BaseClient):
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        super().__init__(mode, api_key=api_key, timeout=timeout, service_name="scraper-service", port=8081)

    def polls(self, location: str = "Germany", pretty: Optional[bool] = False) -> dict:
        location = location.lower()
        endpoint = f"/polls/{location}"
        return self.get(endpoint)
    
    def legislation(self, location: str = "Germany", pretty: Optional[bool] = False) -> dict:
        location = location.lower()
        endpoint = f"/legislation/{location}"
        return self.get(endpoint)
    
    def economic(self, location: str = "Germany", indicators: List[str] = ["GDP+GDP_GROWTH"], pretty: Optional[bool] = False) -> dict:
        location = location.lower()
        endpoint = f"/economic/{location}"
        return self.get(endpoint)