from .client_base import BaseClient
from typing import List, Optional
from pydantic import BaseModel
from .models.searxng import SearXngResults, SearXngResponse

class Search(BaseClient):
    """
    Search for articles using the SearXng API.
    Result format (from models.searxng.SearXngResults):
        url: str
        title: str
        content : str
        publishedDate : Optional[str] = None
        thumbnail : Optional[str] = None
        engine : str
        parsed_url : List[str]
        template : str
        engines : List[str]
        positions : List[int]
        score : float
        category : str
    """
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        super().__init__(mode, api_key=api_key, timeout=timeout, service_name="engine-searxng", port=8021)

    def engine(self, query: str, engine: Optional[str] = "google", pretty: Optional[bool] = False,
               categories: Optional[str] = None, language: Optional[str] = None, time_range: Optional[str] = None) -> List[SearXngResults]:
        """
        Perform a search using the specified engine with additional parameters.
        Time range is one of: [ day, month, year ]

        """
        endpoint = "/search"
        params = {
            "q": query,
            "format": "json",
            "engine": engine,
            "categories": categories,
            "language": language,
            "time_range": time_range
        }
        response = self.get(endpoint, params={k: v for k, v in params.items() if v is not None})
        articles = [SearXngResults(**article) for article in response["results"]]
        return articles

    def image(self, query: str, pretty: Optional[bool] = False, safesearch: Optional[int] = 1,
              image_proxy: Optional[bool] = True) -> List[SearXngResults]:
        """
        Perform an image search with specific presets for images.
        """
        endpoint = "/search"
        params = {
            "q": query,
            "format": "json",
            "categories": "images",
            "safesearch": safesearch,
            "image_proxy": image_proxy
        }
        response = self.get(endpoint, params={k: v for k, v in params.items() if v is not None})
        images = [SearXngResults(**image) for image in response["results"]]
        return images

    def search(self, query: str, categories: Optional[str] = None, engines: Optional[str] = None,
               language: Optional[str] = None, page: Optional[int] = 1, time_range: Optional[str] = None,
               format: Optional[str] = "json", results_on_new_tab: Optional[int] = 0,
               image_proxy: Optional[bool] = None, autocomplete: Optional[str] = None,
               safesearch: Optional[int] = None, theme: Optional[str] = "simple",
               enabled_plugins: Optional[List[str]] = None, disabled_plugins: Optional[List[str]] = None,
               enabled_engines: Optional[List[str]] = None, disabled_engines: Optional[List[str]] = None) -> List[SearXngResults]:
        """
        Perform a search using the SearXng API with additional parameters.
        """
        endpoint = "/search"
        params = {
            "q": query,
            "categories": categories,
            "engines": engines,
            "language": language,
            "pageno": page,
            "time_range": time_range,
            "format": format,
            "results_on_new_tab": results_on_new_tab,
            "image_proxy": image_proxy,
            "autocomplete": autocomplete,
            "safesearch": safesearch,
            "theme": theme,
            "enabled_plugins": enabled_plugins,
            "disabled_plugins": disabled_plugins,
            "enabled_engines": enabled_engines,
            "disabled_engines": disabled_engines
        }
        response = self.get(endpoint, params={k: v for k, v in params.items() if v is not None})
        articles = [SearXngResults(**article) for article in response["results"]]
        return articles