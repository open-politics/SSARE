from fastapi.responses import JSONResponse
import xml.etree.ElementTree as ET
from typing import List
import sdmx
from fastapi import Query
import logging
import aiohttp
from prefect import task

# Import the country to ISO mapping from a separate file
from .mapping import COUNTRY_TO_ISO

logger = logging.getLogger(__name__)

@task
async def fetch_oecd_econ_data(indicators: List[str] = Query(["B1GQ+B1GQ"])):
    logger.debug(f"fetch_oecd_econ_data called with indicators: {indicators}")
    
    indicator_mapping = {
        "GDP": "B1GQ",
        "GDP_GROWTH": "B1GQ_R_GR",
    }

    formatted_data = []

    for state, iso_code in COUNTRY_TO_ISO.items():
        logger.info(f"Fetching data for {state} with ISO code: {iso_code}")
        
        # Map the requested indicators to their SDMX codes
        sdmx_indicators = [indicator_mapping.get(ind, ind) for ind in indicators]
        indicators_query = '+'.join(sdmx_indicators)
        
        url = f'https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAAG@DF_NAAG_I,1.0/A.{iso_code}.{indicators_query}..?startPeriod=2000&dimensionAtObservation=AllDimensions'
        logger.debug(f"Constructed URL: {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={'Accept': 'application/vnd.sdmx.data+json; charset=utf-8; version=1.0'}) as response:
                logger.info(f"API response status code for {state}: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"Received data structure for {state}: {data.keys()}")
                    
                    observations = data['data']['dataSets'][0]['observations']
                    time_periods = data['data']['structure']['dimensions']['observation'][5]['values']
                    
                    logger.debug(f"Number of observations for {state}: {len(observations)}")
                    logger.debug(f"Number of time periods for {state}: {len(time_periods)}")
                    
                    for i, period in enumerate(time_periods):
                        period_data = {'name': period['name'], 'country': state}
                        for index, indicator in enumerate(indicators):
                            sdmx_code = sdmx_indicators[index]
                            key = f'0:0:{index}:{index}:0:{i}'
                            value = observations.get(key, [None])[0]
                            logger.debug(f"Period: {period['name']}, Indicator: {indicator}, Key: {key}, Value: {value}")
                            if value is not None:
                                period_data[indicator] = value
                        formatted_data.append(period_data)
                    
                    logger.info(f"Formatted data length for {state}: {len(formatted_data)}")
                else:
                    error_text = await response.text()
                    logger.error(f"Failed to retrieve data for {state}: {response.status}")
                    logger.error(f"Response content for {state}: {error_text}")

    return formatted_data
