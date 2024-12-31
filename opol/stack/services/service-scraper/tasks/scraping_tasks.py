from prefect import task
from news_sites.cnn import CNNScraper
from news_sites.dw import DWScraper  # Assume you have this scraper
from news_sites.bbc import BBCScraper  # If implemented

@task(name="Scrape CNN Articles", retries=3, retry_delay_seconds=60)
async def scrape_cnn_articles():
    scraper = CNNScraper()
    df = await scraper.scrape()
    return df

@task(name="Scrape DW Articles", retries=3, retry_delay_seconds=60)
async def scrape_dw_articles():
    scraper = DWScraper()
    df = await scraper.scrape()
    return df

@task(name="Scrape BBC Articles", retries=3, retry_delay_seconds=60)
async def scrape_bbc_articles():
    scraper = BBCScraper()
    df = await scraper.scrape()
    return df