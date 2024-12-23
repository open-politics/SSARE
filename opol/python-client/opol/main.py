from .api.articles import Articles
from .api.entities import Entities
from .api.geo import Geo
from .api.classification import Classification
from .api.scraping import Scraping
from .api.legislation import Legislation
import os

class OPOL:
    """
    Main API client to interact with all OPOL services.
    """
    def __init__(
            self, 
            mode: str = None, 
            api_key: str = None, 
            timeout: int = 60, 
            provider: str = "Google", 
            model_name: str = "models/gemini-1.5-flash-latest", 
            llm_api_key: str = None):
        
        mode = mode if mode else os.getenv('OPOL_MODE', 'remote')

        # Opol Services
        self.geo = Geo(mode, api_key, timeout=timeout)
        self.articles = Articles(mode, api_key, timeout=timeout)
        self.entities = Entities(mode, api_key, timeout=timeout)
        self.scraping = Scraping(mode, api_key, timeout=timeout)
        self.legislation = Legislation(mode, api_key, timeout=timeout)

        # Classification Service (usage with Ollama or LLM provider)
        self.classification = Classification(mode, api_key, timeout=timeout, provider=provider, model_name=model_name, llm_api_key=llm_api_key)