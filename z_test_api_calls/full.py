import requests
import time
import json

from pydantic import BaseModel, Field
from typing import List, Optional, Dict


class ArticleBase(BaseModel):
    url: str = Field(...)
    headline: str = Field(...)
    paragraphs: List[str] = Field(...)
    source: Optional[str] = None  # Extendable field for the article's source

    class Config:
        orm_mode = True


# URLs of services
SCRAPER_SERVICE_URL = 'http://localhost:8081'
POSTGRES_SERVICE_URL = 'http://localhost:5432'
NLP_SERVICE_URL = 'http://localhost:0420'
QDRANT_SERVICE_URL = 'http://localhost:6333'


# Step 0: Produce Flags
flags_response = requests.get(f"{POSTGRES_SERVICE_URL}/flags")
assert flags_response.status_code == 200
print("Flags produced...")

# Step 1: Trigger the scraping job
scrape_response = requests.post(f"{SCRAPER_SERVICE_URL}/create_scrape_jobs")
assert scrape_response.status_code == 200
print("Scraping job triggered...")

# Step 2: Wait for scraping to complete (this is a simplification)
time.sleep(10)  # Adjust the sleep time as necessary for your scrape job

# Step 3: Trigger processing of raw articles
process_response = requests.get(f"{POSTGRES_SERVICE_URL}/receive_raw_articles")
print(process_response)
print("Processing of raw articles triggered...")

# Step 4: Fetch unprocessed articles from PostgreSQL
articles_response = requests.get(f"{POSTGRES_SERVICE_URL}/articles")
print(articles_response)
articles = articles_response.json()['articles']

# Validate articles structure
for article in articles:
    ArticleBase(**article)

print("Articles fetched and validated...")

# Step 5: Send articles to NLP service for embedding creation
embeddings_response = requests.post(f"{NLP_SERVICE_URL}/create_embeddings", json=articles)
assert embeddings_response.status_code == 200
print("NLP processing and embeddings creation triggered...")

# Step 6: Store processed articles and embeddings in PostgreSQL and Qdrant

## Step 6.1: Store in PostgreSQL
store_response = requests.post(f"{POSTGRES_SERVICE_URL}/store_articles_with_embeddings")

## Step 6.2: Store in Qdrant



# Assuming you have an endpoint to trigger this
# The specifics of this request depend on how you've implemented the Qdrant storage logic
# Replace with the correct endpoint and logic as necessary
store_response = requests.post(f"{QDRANT_SERVICE_URL}/store_vectors", json=articles)
assert store_response.status_code == 200
print("Processed articles and embeddings stored in PostgreSQL and Qdrant...")

print("Full test run completed.")
