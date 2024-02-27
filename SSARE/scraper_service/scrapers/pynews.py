import asyncio
import pandas as pd
from bs4 import BeautifulSoup
import aiohttp
import os
from urllib.parse import urlparse
directory_path = "/app/scrapers/data/dataframes"
if not os.path.exists(directory_path):
    os.makedirs(directory_path)

# Function to fetch news URLs from the Python News API
async def fetch_news(session, api_key, total_articles=300):
    articles = []
    page = 1
    pageSize = 100  # Max allowed by API
    while len(articles) < total_articles:
        url = f'https://newsapi.org/v2/top-headlines?category=general&pageSize={pageSize}&page={page}&apiKey={api_key}'
        async with session.get(url) as response:
            data = await response.json()
            fetched_articles = data.get('articles', [])
            filtered_articles = [(article['url'], article['title']) for article in fetched_articles if 'news.google.com' not in article['url']]
            articles.extend(filtered_articles)
            # Break if no more articles are returned
            if not fetched_articles:
                break
            page += 1
    return articles[:total_articles]

# Async function to process each article URL
async def process_article_url(session, url):
    try:
        async with session.get(url) as response:
            article_data = await response.text()
            article_soup = BeautifulSoup(article_data, features="html.parser")
            headline = article_soup.find('h1')
            headline_text = headline.text.strip() if headline else 'N/A'
            article_paragraphs = article_soup.find_all('p')
            cleaned_paragraph = ' '.join([p.text.strip() for p in article_paragraphs])
            print(f"Processed {url}")
            
            parsed_url = urlparse(url)
            import re
            source = re.sub(r'^www.', '', parsed_url.netloc)
            
            return {'url': url, 'headline': headline_text, 'paragraphs': cleaned_paragraph, 'source': source}
    except Exception as e:
        print(f"Failed to process {url}: {e}")
        return {'url': url, 'headline': 'N/A', 'paragraphs': '', 'source': 'N/A'}

async def main(api_key):
    async with aiohttp.ClientSession() as session:
        news_urls = await fetch_news(session, api_key)
        tasks = [process_article_url(session, url) for url, _ in news_urls]
        articles = await asyncio.gather(*tasks)
        df = pd.DataFrame(articles)
        df.to_csv(f"{directory_path}/pynews_articles.csv", index=False)
        print(df.head(3))

if __name__ == "__main__":
    api_key = '47d333159d8745c1b51cacd5440d65c1'  # Replace with your actual News API key
    asyncio.run(main(api_key))
