from .api.articles import Articles
from .api.entities import Entities
from .api.geo import Geo
from .api.classification import Classification

class OPOL:
    """
    Main API client to interact with all OPOL services.
    """
    def __init__(self, mode: str = "remote", api_key: str = None, timeout: int = 60):
        self.geo = Geo(mode, api_key, timeout=timeout)
        self.articles = Articles(mode, api_key, timeout=timeout)
        self.entities = Entities(mode, api_key, timeout=timeout)
        self.classification = Classification(mode, api_key, timeout=timeout)
