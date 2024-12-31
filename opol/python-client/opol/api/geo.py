from typing import List, Optional
from pydantic import BaseModel
import json

from .client_base import BaseClient

class Geo(BaseClient):
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        super().__init__(mode, api_key=api_key, timeout=timeout, service_name="service-geo", port=3690)

    class ByIdRequest(BaseModel):
        content_ids: List[str]

    def __call__(self, *args, **kwargs):
        if args:
            kwargs['ids'] = args[0]
        return self.by_id(*args, **kwargs)
    
    def json_by_event(self, event_type: str, limit: Optional[int] = 100, pretty: Optional[bool] = False) -> dict:
        endpoint = f"geojson_events/{event_type}?limit={limit}"
        if pretty:
            response = self.get(endpoint)
            print(json.dumps(response, indent=4))
            return response
        else:
            return self.get(endpoint)
    
    def code(self, location: str) -> dict:
        endpoint = f"geocode_location?location={location}"
        return self.get(endpoint)

    def get_geojson(self, type: str = "Politics") -> dict:
        endpoint = f"geojson_events/{type}"
        return self.get(endpoint)
    
    def by_id(self, ids: List[str], pretty: bool = False) -> dict:
        endpoint = "geojson_by_content_ids"
        request = self.ByIdRequest(content_ids=ids)
        params = request.model_dump()
        if pretty:
            response = self.post(endpoint, json=params)
            print(json.dumps(response, indent=4))
            return response
        else:
            return self.post(endpoint, json=params)
