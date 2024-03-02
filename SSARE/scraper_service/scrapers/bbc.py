import asyncio
import aiohttp
from bs4 import BeautifulSoup
import pandas as pd

# Async function to fetch the HTML content of a given URL using aiohttp instead of requests
async def fetch_html_content(session, url):
    async with session.get(url) as response:
        return await response.text()

# Function to extract article URLs from the BBC News World page (kept synchronous since it processes HTML content locally)
def extract_article_urls(page_html):
    soup = BeautifulSoup(page_html, 'html.parser')
    article_elements = soup.find_all('li', class_='ssrcss-13h7haz-ListItem')
    article_urls = [element.find('a', class_='ssrcss-1mrs5ns-PromoLink')['href'] for element in article_elements if element.find('a', class_='ssrcss-1mrs5ns-PromoLink')]
    return article_urls

# Function to extract paragraphs from an article page (kept synchronous for the same reason as above)
def extract_paragraphs(article_html):
    soup = BeautifulSoup(article_html, 'html.parser')
    paragraphs = soup.find_all('p')
    return [paragraph.text for paragraph in paragraphs]

# Async function to process each article URL
async def process_article_url(session, base_url, article_url):
    full_article_url = f"{base_url}{article_url}" if not article_url.startswith(base_url) else article_url
    article_html = await fetch_html_content(session, full_article_url)
    paragraphs = extract_paragraphs(article_html)
    # Assuming headline can be extracted similarly (update selector as needed)
    headline = 'N/A'
    soup = BeautifulSoup(article_html, 'html.parser')
    headline_element = soup.find('h1')
    if headline_element:
        headline = headline_element.text.strip()
    return {'url': full_article_url, 'headline': headline, 'paragraphs': paragraphs, 'source': 'bbc'}

# Main async script
async def main():
    base_url = 'https://www.bbc.com'
    news_page_url = f"{base_url}/news/world"
    async with aiohttp.ClientSession() as session:
        news_page_html = await fetch_html_content(session, news_page_url)
        article_urls = extract_article_urls(news_page_html)
        tasks = [process_article_url(session, base_url, url) for url in article_urls]
        articles = await asyncio.gather(*tasks)
        df = pd.DataFrame(articles)

        # Show the DataFrame head
        print(df.head())

if __name__ == "__main__":
    asyncio.run(main())

