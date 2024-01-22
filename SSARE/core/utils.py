import configparser
import os
from typing import Optional



def load_config(config_dir: Optional[str] = None) -> configparser.ConfigParser:
    """Load the configuration file."""
    config = configparser.ConfigParser()
    if not config_dir:
        config_dir = get_data_path()
    config.read(os.path.join(config_dir, "config.ini"))
    return config


def get_data_path() -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "data",
    )