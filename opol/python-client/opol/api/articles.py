import json
from typing import Dict, List, Optional
from pydantic import BaseModel

from .client_base import BaseClient

class Articles(BaseClient):
    """
    Client to interact with the Articles API endpoints.
    """
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        # service-postgres at port 5434
        super().__init__(mode, api_key=api_key, timeout=timeout, service_name="service-postgres", port=5434)

    def __call__(self, *args, **kwargs):
        if args:
            kwargs['query'] = args[0]
        return self.get_articles(*args, **kwargs)
    
    class GetArticlesRequest(BaseModel):
        query: str
        limit: Optional[int] = 10
        from_date: Optional[str] = None
        to_date: Optional[str] = None
        search_type: Optional[str] = None
        entities: Optional[List[str]] = None
        pretty: Optional[bool] = False

    class GetArticlesResponse(BaseModel):
        contents: List[Dict]
        total: int

    def get_articles(self, *args, **kwargs) -> GetArticlesResponse:
        if args and 'query' not in kwargs:
            kwargs['query'] = args[0]
        
        # Just the relative endpoint now
        endpoint = "contents"  
        request = self.GetArticlesRequest(**kwargs)
        params = {k: v for k, v in request.model_dump(exclude={"pretty"}).items() if v is not None}

        if request.pretty:
            response = self.get(endpoint, params)
            print(json.dumps(response, indent=4))
            return response
        else:
            return self.get(endpoint, params)

    def by_entity(self, entity_name: str, skip: int = 0, limit: int = 10) -> Dict:
        endpoint = f"v2/contents_by_entity/{entity_name}"
        params = {"skip": skip, "limit": limit}
        return self.get(endpoint, params)
