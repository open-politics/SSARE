from .client_base import BaseClient
from typing import List, Optional
from pydantic import BaseModel
import json

class GeoJSON(BaseClient):
    def __init__(self, mode: str, base_url: str, api_key: str = None):
        super().__init__(mode, base_url, api_key)

    def __call__(self, *args, **kwargs):
        if args:
            kwargs['ids'] = args[0]
        return self.by_id(*args, **kwargs)
    
    def get_geojson(self, type: str = "Politics") -> dict:
        endpoint = f"geo-service/geojson_events/{type}"
        return self.get(endpoint)
    
    class ByIdRequest(BaseModel):
        content_ids: List[str]
    
    def by_id(self, ids: List[str], pretty: bool = False) -> dict:
        endpoint = f":3690" + "/geojson_by_content_ids" if self.mode == "local" else "/geo-service/geojson_by_content_ids"
        request = self.ByIdRequest(content_ids=ids)
        params = request.model_dump()
        print("Request payload:", params)
        if pretty:
            print(json.dumps(self.post(endpoint, json=params), indent=4))
        else:
            return self.post(endpoint, json=params)
    

    def by_event(self, event_type: str, limit: Optional[int] = 100, pretty: Optional[bool] = False) -> dict:
        endpoint = f":3690" + f"/geojson_events/{event_type}?limit={limit}" if self.mode == "local" else f"/geo-service/geojson_events/{event_type}"
        if pretty:
            print(json.dumps(self.get(endpoint), indent=4))
        else:
            return self.get(endpoint)   