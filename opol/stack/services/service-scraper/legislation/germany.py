import json
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import xml.etree.ElementTree as ET
from prefect import task
from pydantic import BaseModel
from typing import List, Optional
from fastapi import APIRouter

router = APIRouter()

class LegislationItem(BaseModel):
    law: Optional[str]
    status: Optional[str]
    label: Optional[str]
    date: Optional[str]
    initiative: Optional[str]
    href: Optional[str]

@task
def get_german_legislation() -> List[LegislationItem]:
    api_key = "I9FKdCn.hbfefNWCY336dL6x62vfwNKpoN2RZ1gp21"
    endpoint = "https://search.dip.bundestag.de/api/v1/vorgang"

    params = {
        "apikey": api_key,
    }
    headers = {
        "Content-Type": "application/json",
    }
    response = requests.get(endpoint, headers=headers, params=params)
    response.raise_for_status()
    
    data = response.json()
    results = []
    
    for item in data.get('documents', []):
        status = item.get('beratungsstand')
        if status == 'Noch nicht beantwortet':
            label = 'yellow'
        elif status == 'Beantwortet':
            label = 'green'
        else:
            label = 'red'
        
        # Construct the href link using the fundstelle field
        id = item.get('id')
        href = f"https://dip.bundestag.de/suche?term={id}&f.wahlperiode=20&rows=25"
        
        # Handle the initiative field which might be a list
        initiative = item.get('initiative')
        if isinstance(initiative, list):
            initiative = ', '.join(initiative)  # Convert list to a comma-separated string
        
        results.append(LegislationItem(
            law=item.get('titel'),
            status=status,
            label=label,
            date=item.get('datum'),
            initiative=initiative,
            href=href
        ))
    
    results.sort(key=lambda x: x.label)

    return results

@router.get("/germany", response_model=List[LegislationItem])
async def get_germany_legislation():
    return get_german_legislation()