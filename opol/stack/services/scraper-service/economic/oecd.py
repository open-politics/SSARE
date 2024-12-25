from fastapi.responses import JSONResponse
import xml.etree.ElementTree as ET
from typing import List
import sdmx
from fastapi import Query
import logging
import aiohttp
from functools import lru_cache
from prefect import task
from fastapi import APIRouter
from .mapping import COUNTRY_TO_ISO

router = APIRouter()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

COUNTRY_TO_ISO_LOWER = {k.lower(): v for k, v in COUNTRY_TO_ISO.items()}

def get_iso_code(state: str) -> str:
    state = state.lower()
    return COUNTRY_TO_ISO_LOWER.get(state)

@task
async def get_econ_data(state: str = "Germany", indicators: List[str] = Query(["GDP", "GDP_GROWTH"])):
    logger.debug(f"get_econ_data called with state: {state}, indicators: {indicators}")
    
    indicator_mapping = {
        "GDP": "B1GQ",
        "GDP_GROWTH": "B1GQ_R_GR",
    }

    iso_code = get_iso_code(state)
    if not iso_code:
        logger.error(f"No ISO code found for country: {state}")
        raise ValueError(f"No ISO code found for country: {state}")
    
    logger.info(f"ISO code for {state}: {iso_code}")
    
    # Map the requested indicators to their SDMX codes
    sdmx_indicators = [indicator_mapping.get(ind, ind) for ind in indicators]
    indicators_query = '+'.join(sdmx_indicators)
    
    url = f'https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAAG@DF_NAAG_I,1.0/A.{iso_code}.{indicators_query}..?startPeriod=2000&dimensionAtObservation=AllDimensions'
    logger.debug(f"Constructed URL: {url}")
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={'Accept': 'application/vnd.sdmx.data+json; charset=utf-8; version=1.0'}) as response:
            logger.info(f"API response status code: {response.status}")
            
            if response.status == 200:
                data = await response.json()
                logger.debug(f"Received data structure: {data.keys()}")
                
                observations = data['data']['dataSets'][0]['observations']
                time_periods = data['data']['structure']['dimensions']['observation'][5]['values']
                
                logger.debug(f"Number of observations: {len(observations)}")
                logger.debug(f"Number of time periods: {len(time_periods)}")
                
                formatted_data = []
                for i, period in enumerate(time_periods):
                    period_data = {'year': period['name']}
                    for index, indicator in enumerate(indicators):
                        sdmx_code = sdmx_indicators[index]
                        key = f'0:0:{index}:{index}:0:{i}'
                        value = observations.get(key, [None])[0]
                        logger.debug(f"Period: {period['name']}, Indicator: {indicator}, Key: {key}, Value: {value}")
                        if value is not None:
                            period_data[indicator] = value
                    formatted_data.append(period_data)
                
                logger.info(f"Formatted data length: {len(formatted_data)}")
                return formatted_data
            else:
                error_text = await response.text()
                logger.error(f"Failed to retrieve data: {response.status}")
                logger.error(f"Response content: {error_text}")
                return []
    
@router.get("/{location}")
async def get_oecd_data(location: str = "Germany", indicators: List[str] = Query(["B1GQ+B1GQ"])):
    return await get_econ_data(location, indicators)

#  For future 
#     url_cpi = f'https://sdmx.oecd.org/public/rest/data/OECD.SDD.TPS,DSD_PRICES@DF_PRICES_ALL,/.M.{iso_code}.CPI.PA._T.N.GY?startPeriod=2000&dimensionAtObservation=AllDimensions'
