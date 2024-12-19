from abc import ABC
from typing import Dict, Any
import httpx
import logging
from urllib.parse import urljoin
import os

from .url_strategy import RemoteURLBuilder, LocalURLBuilder, ContainerURLBuilder

logger = logging.getLogger(__name__)

class BaseClient(ABC):
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60,
                 service_name: str = None, port: int = None):
        self.mode = mode if mode else os.getenv('OPOL_MODE', 'remote')
        self.api_key = api_key
        self.timeout = timeout
        self.service_name = service_name
        self.port = port
        self.client = httpx.Client(timeout=timeout)

        # Choose the URL builder strategy
        if mode == "remote":
            self.url_builder = RemoteURLBuilder()
        elif mode == "local":
            self.url_builder = LocalURLBuilder()
        elif mode == "container":
            self.url_builder = ContainerURLBuilder()
        else:
            raise ValueError(f"Unsupported mode: {mode}")

    def get_base_url(self) -> str:
        return self.url_builder.build_base_url(self.service_name, self.port)

    def build_url(self, endpoint: str) -> str:
        # Ensure endpoint does not start with a slash
        endpoint = endpoint.lstrip('/')
        base_url = self.get_base_url()
        # Use a simple join since we ensured trailing slash on base and no leading slash on endpoint
        return base_url + endpoint

    def get(self, endpoint: str, params: Dict[str, Any] = None) -> Any:
        headers = {}
        if self.api_key:
            headers['apikey'] = self.api_key  
        full_url = self.build_url(endpoint)
        try:
            response = self.client.get(full_url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred: {e} for URL: {full_url}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error occurred: {e} for URL: {full_url}")
            raise

    def post(self, endpoint: str, json: Dict[str, Any] = None) -> Any:
        headers = {}
        if self.api_key:
            headers['apikey'] = self.api_key  
        full_url = self.build_url(endpoint)
        try:
            response = self.client.post(full_url, json=json, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred: {e} for URL: {full_url}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error occurred: {e} for URL: {full_url}")
            raise

    def close(self):
        self.client.close()
