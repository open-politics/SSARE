from .api.articles import Articles
from .api.entities import Entities
from .api.geojson import GeoJSON
from .api.classification import Classification
from .api.client_base import BaseClient

class OPOL(BaseClient):
    """
    Main API client to interact with all opol services.
    """
    def __init__(self, mode: str = "remote", base_url: str = None, api_key: str = None, timeout: int = 60):
        if mode == "remote":
            base_url = base_url or "https://api.opol.io"
        else:
            base_url = base_url or "http://localhost"

        super().__init__(mode, base_url, api_key, timeout)

        self.articles = Articles(mode, base_url, api_key)
        self.entities = Entities(mode, base_url, api_key)
        self.geojson = GeoJSON(mode, base_url, api_key)
        self.classification = Classification(mode, base_url, api_key)