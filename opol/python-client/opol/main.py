from .api.articles import Articles
from .api.entities import Entities
from .api.geo import Geo
from .api.classification import Classification
import os

class OPOL:
    """
    Main API client to interact with all OPOL services.
    """
    def __init__(self, mode: str = None, api_key: str = None, timeout: int = 60):
        mode = mode if mode else os.getenv('OPOL_MODE', 'remote')
        self.geo = Geo(mode, api_key, timeout=timeout)
        self.articles = Articles(mode, api_key, timeout=timeout)
        self.entities = Entities(mode, api_key, timeout=timeout)
        self.classification = Classification(mode, api_key, timeout=timeout)
