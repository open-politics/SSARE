# cnn_scraper.py

import asyncio
import pandas as pd
from bs4 import BeautifulSoup
import aiohttp
import os

async def scrape_cnn_articles(session):
    base_url = 'https://www.cnn.com'
    async with session.get(base_url) as response:
        data = await response.text()
        soup = BeautifulSoup(data, features="html.parser")
        all_urls = [base_url + a['href'] for a in soup.find_all('a', href=True) 
                    if a['href'] and a['href'][0] == '/' and a['href'] != '#']
    def url_is_article(url, current_year='2023'):
        return ('cnn.com/{}/'.format(current_year) in url and 
                '/politics/' in url and 
                '/video/' not in url)

    article_urls = [url for url in all_urls if url_is_article(url)]
    tasks = [process_article_url(session, url) for url in article_urls]
    articles = await asyncio.gather(*tasks)
    return pd.DataFrame(articles, columns=['url', 'title', 'text_content', 'source', 'content_type'])

# Async function to process each article URL
async def process_article_url(session, url):
    try:
        async with session.get(url) as response:
            article_data = await response.text()
            article_soup = BeautifulSoup(article_data, features="html.parser")
            headline = article_soup.find('h1', class_='headline__text')
            headline_text = headline.text.strip() if headline else 'N/A'
            article_paragraphs = article_soup.find_all('div', class_='article__content')
            cleaned_paragraphs = ' '.join([p.text.strip() for p in article_paragraphs])
            source = 'cnn'
            content_type = 'article'
            print(f"Processed {url}")
            
            return url, headline_text, cleaned_paragraphs, source, content_type
    except Exception as e:
        print(f"Failed to scrape {url}: {str(e)}")
        return url, 'N/A', '', 'cnn', 'article'

async def main():
    async with aiohttp.ClientSession() as session:
        df = await scrape_cnn_articles(session)
        os.makedirs('/app/scrapers/data', exist_ok=True)
        df.to_csv('/app/scrapers/data/cnn_contents.csv', index=False)
        print(df.head(3))

if __name__ == "__main__":
    asyncio.run(main())
