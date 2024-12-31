from prefect import task
from core.models import Content
from typing import List
import pandas as pd

@task
def process_scraped_data(df: pd.DataFrame) -> List[Content]:
    contents = []
    for record in df.to_dict(orient='records'):
        content = Content(**record)
        contents.append(content)
    return contents