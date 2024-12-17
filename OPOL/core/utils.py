from configparser import ConfigParser
import os
from typing import Optional
import json
from uuid import UUID
import logging
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config():
    config = ConfigParser()
    config.read('core/configs/config.conf')
    return config


def get_data_path() -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "data",
    )

class DimensionRequest(BaseModel):
    name: str
    description: str
    type: str

class UUIDEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, UUID):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

class DimensionRequestEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (BaseModel, DimensionRequest)):
            return obj.dict()
        if isinstance(obj, UUID):
            return str(obj)
        return json.JSONEncoder.default(self, obj)

def get_db_url():
    if  os.getenv('DB_MODE') == "managed":
        return (
            f"postgresql+asyncpg://{os.getenv('MANAGED_ARTICLES_DB_USER')}:{os.getenv('MANAGED_ARTICLES_DB_PASSWORD')}"
                f"@{os.getenv('MANAGED_ARTICLES_DB_HOST')}:{os.getenv('MANAGED_ARTICLES_DB_PORT')}/{os.getenv('ARTICLES_DB_NAME')}"
            )
    else:
            return (
                f"postgresql+asyncpg://{os.getenv('ARTICLES_DB_USER')}:{os.getenv('ARTICLES_DB_PASSWORD')}"
            f"@articles_database:{os.getenv('ARTICLES_DB_PORT')}/{os.getenv('ARTICLES_DB_NAME')}"
        )

def get_redis_url():
    if os.getenv('REDIS_MODE') == "managed":
        return f"redis://{os.getenv('MANAGED_REDIS_HOST')}:{os.getenv('MANAGED_REDIS_PORT')}"
    else:
        return f"redis://redis:{os.getenv('REDIS_PORT')}"

