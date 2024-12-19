from .client_base import BaseClient
from typing import List, Optional
from pydantic import BaseModel
import json

class Geo(BaseClient):
    def __init__(self, mode: str, api_key: str = None):
        super().__init__(mode, api_key)

    def get_service_name(self) -> str:
        return "geo-service"

    def get_port(self) -> int:
        return 3690

    def json_by_event(self, event_type: str, limit: int = 100, pretty: Optional[bool] = False) -> dict:
        endpoint = f"/geojson_events/{event_type}?limit={limit}"
        full_url = self.build_url(endpoint)
        if pretty:
            print(json.dumps(self.get(full_url), indent=4))
        else:
            return self.get(full_url)

    def code(self, location: str) -> dict:
        endpoint = f"/geocode_location?location={location}"
        full_url = self.build_url(endpoint)
        return self.get(full_url)

    def __call__(self, *args, **kwargs):
        if args:
            kwargs['ids'] = args[0]
        return self.by_id(*args, **kwargs)
    
    def get_geojson(self, type: str = "Politics") -> dict:
        endpoint = f"/geojson_events/{type}"
        return self.get(endpoint)
    
    class ByIdRequest(BaseModel):
        content_ids: List[str]
    
    def by_id(self, ids: List[str], pretty: bool = False) -> dict:
        endpoint = "/geojson_by_content_ids"
        request = self.ByIdRequest(content_ids=ids)
        params = request.model_dump()
        print("Request payload:", params)
        if pretty:
            print(json.dumps(self.post(endpoint, json=params), indent=4))
        else:
            return self.post(endpoint, json=params)
    

    def json_by_event(self, event_type: str, limit: Optional[int] = 100, pretty: Optional[bool] = False) -> dict:
        endpoint = f":3690" + f"/geojson_events/{event_type}?limit={limit}" if self.mode == "local" else f"/geo-service/geojson_events/{event_type}"
        if pretty:
            print(json.dumps(self.get(endpoint), indent=4))
        else:
            return self.get(endpoint)   
    
    def code(self, location: str) -> dict:
        endpoint = f":3690" + f"/geocode_location?location={location}" if self.mode == "local" else f"/geo-service/geocode_location"
        return self.get(endpoint)
    
