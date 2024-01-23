from configparser import ConfigParser
import os
from typing import Optional



def load_config():
    config = ConfigParser()
    config.read('config.ini')
    return config


def get_data_path() -> str:
    return os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "data",
    )