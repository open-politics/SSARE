import json
from .client_base import BaseClient
from typing import Dict, List, Optional
from pydantic import BaseModel
from enum import Enum

class Articles(BaseClient):
    """
    Client to interact with the Articles API endpoints.
    """
    def __init__(self, mode: str, base_url: str, api_key: str = None):
        super().__init__(mode, base_url, api_key)

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
            # If a positional argument is provided and 'query' is not in kwargs, use the first positional argument as 'query'
            kwargs['query'] = args[0]
        
        endpoint = f":5434" + "/v2/contents" if self.mode == "local" else "/postgres-service/contents"
        print(endpoint)
        request = self.GetArticlesRequest(**kwargs)
        params = request.model_dump(exclude={"pretty"})
        params = {k: v for k, v in request.model_dump(exclude={"pretty"}).items() if v is not None}
        print(params)
        if request.pretty:
            # print pretty json
            print(json.dumps(self.get(endpoint, params), indent=4))
        else:
            return self.get(endpoint, params)

    def get_articles_by_entity(self, entity_name: str, skip: int = 0, limit: int = 10) -> Dict:
        endpoint = f"/postgres-service/routes/search/contents_by_entity/{entity_name}"
        params = {"skip": skip, "limit": limit}
        return self.get(endpoint, params)

