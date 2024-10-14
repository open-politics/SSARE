# dw_scraper.py

import asyncio
import pandas as pd
from bs4 import BeautifulSoup
import aiohttp
import os

async def scrape_dw_articles(session, base_url):
    async with session.get(base_url) as response:
        data = await response.text()
        soup = BeautifulSoup(data, features="html.parser")
        all_urls = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith('/en/')]
        full_urls = [url if url.startswith('http') else base_url + url for url in all_urls]
        article_urls = set(full_urls)  # Use set to avoid duplicate URLs

    tasks = [process_article_url(session, url, base_url) for url in article_urls]
    articles = await asyncio.gather(*tasks)
    return pd.DataFrame(articles, columns=['url', 'title', 'text_content', 'source', 'content_type'])

# Async function to process each article URL
async def process_article_url(session, url, base_url):
    try:
        async with session.get(url) as response:
            article_data = await response.text()
            article_soup = BeautifulSoup(article_data, features="html.parser")
            headline = article_soup.find('h1')
            headline_text = headline.text.strip() if headline else 'N/A'
            article_paragraphs = article_soup.find_all('p')
            cleaned_paragraphs = ' '.join([p.text.strip() for p in article_paragraphs])
            source = base_url
            content_type = 'article'
            print(f"Processed {url}")
            
            return url, headline_text, cleaned_paragraphs, source, content_type
    except Exception as e:
        print(f"Failed to scrape {url}: {str(e)}")
        return url, 'N/A', '', base_url, 'article'

async def main():
    base_url = 'https://www.dw.com/en/'
    async with aiohttp.ClientSession() as session:
        df = await scrape_dw_articles(session, base_url)
        os.makedirs('/app/scrapers/data', exist_ok=True)
        df.to_csv('/app/scrapers/data/dw_contents.csv', index=False)
        print(df.head(3))

if __name__ == "__main__":
    asyncio.run(main())
