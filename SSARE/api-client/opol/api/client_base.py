import httpx
from typing import Any, Dict
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

class BaseClient:
    def __init__(self, mode: str, base_url: str, api_key: str = None, timeout: int = 60):
        # Validate base URL
        # parsed_url = urlparse(base_url)
        # if not parsed_url.scheme or not parsed_url.netloc:
        #     raise ValueError("Invalid base URL provided.")
        
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.client = httpx.Client(timeout=self.timeout)
        self.mode = mode

    def get(self, endpoint: str, params: Dict[str, Any] = None) -> Any:
        headers = {}
        if self.api_key:
            headers['Authorization'] = f"Bearer {self.api_key}"  # Include API key in headers
        try:
            full_url = f"{self.base_url}{endpoint}"
            response = self.client.get(full_url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred: {e} for URL: {full_url}")
            raise
        except httpx.RequestError as e:
            print(f"Request error occurred: {e} for URL: {full_url}")
            raise

    def post(self, endpoint: str, json: Dict[str, Any] = None) -> Any:
        headers = {}
        if self.api_key:
            headers['Authorization'] = f"Bearer {self.api_key}"  # Include API key in headers
        try:
            request = self.client.build_request("POST", f"{self.base_url}{endpoint}", json=json, headers=headers)
            response = self.client.send(request)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"HTTP error occurred: {e}")
            raise
        except httpx.RequestError as e:
            print(f"Request error occurred: {e}")
            raise

    def close(self):
        self.client.close()