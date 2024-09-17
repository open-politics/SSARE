import asyncio
import pandas as pd
from bs4 import BeautifulSoup
import aiohttp
from playwright.async_api import async_playwright  # Use async API
from urllib.parse import urljoin
import os
from newspaper import Article

# 1. Aiohttp Async Scraping for static pages (Africa, India)
async def scrape_with_bs4(session, base_url, url_filter):
    async with session.get(base_url) as response:
        data = await response.text()
        soup = BeautifulSoup(data, features="html.parser")
        all_urls = [a['href'] for a in soup.find_all('a', href=True) if url_filter in a['href']]
        full_urls = [url if url.startswith('http') else urljoin(base_url, url) for url in all_urls]
        article_urls = set(full_urls)
    
    tasks = [process_article_url(session, url, base_url) for url in article_urls]
    articles = await asyncio.gather(*tasks)
    return pd.DataFrame(articles, columns=['url', 'headline', 'paragraphs', 'source'])

async def process_article_url(session, url, base_url):
    try:
        async with session.get(url) as response:
            article_data = await response.text()
            article_soup = BeautifulSoup(article_data, features="html.parser")
            headline = article_soup.find('h1')
            headline_text = headline.text.strip() if headline else 'N/A'
            article_paragraphs = article_soup.find_all('p')
            cleaned_paragraphs = ' '.join([p.text.strip() for p in article_paragraphs])
            return url, headline_text, cleaned_paragraphs, base_url
    except Exception as e:
        print(f"Failed to scrape {url}: {str(e)}")
        return url, 'N/A', '', base_url

async def async_scraping():
    async with aiohttp.ClientSession() as session:
        urls_to_scrape = [
            ('https://www.hindustantimes.com/', 'politics-news'),
            ('https://www.theafricareport.com/', 'politics'),
        ]
        tasks = [scrape_with_bs4(session, base_url, filter_term) for base_url, filter_term in urls_to_scrape]
        results = await asyncio.gather(*tasks)
        combined_df = pd.concat(results)
        return combined_df

# 2. Playwright Scraping for dynamic content (BBC, Al Jazeera, Buenos Aires Times)
async def scrape_dynamic_articles(page, base_url, url_filter, max_depth=1, current_depth=0):
    if current_depth >= max_depth:
        return []

    links = await page.query_selector_all('a')
    article_urls = [urljoin(base_url, await link.get_attribute('href')) for link in links if await link.get_attribute('href') and url_filter in await link.get_attribute('href')]
    
    data = []
    for url in article_urls:
        print(f"Processing: {url}")
        article = Article(url)
        try:
            article.download()
            article.parse()
            paragraphs = article.text
            data.append({
                "url": url,
                "headline": article.title,
                "paragraphs": paragraphs,
                "source": base_url
            })
        except Exception as e:
            print(f"Failed to process {url}: {str(e)}")
    
    for url in article_urls:
        await page.goto(url)
        data += await scrape_dynamic_articles(page, url, url_filter, max_depth, current_depth + 1)
    
    return data

async def run_playwright_scraping():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # List of dynamic sites with filters
        dynamic_sites = [
            ('https://www.bbc.com/news', 'politics'),
            ('https://www.aljazeera.com/news/', 'politics'),
            ('https://www.batimes.com.ar/', 'politics'),
        ]

        data = []
        for base_url, url_filter in dynamic_sites:
            for attempt in range(3):  # Retry up to 3 times
                try:
                    await page.goto(base_url, timeout=60000)  # Increase timeout to 60 seconds
                    data += await scrape_dynamic_articles(page, base_url, url_filter)
                    break  # Break if successful
                except playwright._impl._errors.TimeoutError:
                    print(f"Timeout while navigating to {base_url}, attempt {attempt + 1}")
                except Exception as e:
                    print(f"Failed to navigate to {base_url}: {str(e)}")
                    break  # Break on other exceptions

        await context.close()
        await browser.close()

        return pd.DataFrame(data)

# Main function to run both async and playwright scrapers
async def main():
    # Run async scraping (static content)
    async_df = await async_scraping()

    # Run dynamic scraping (dynamic content with Playwright)
    dynamic_df = await run_playwright_scraping()

    # Combine the results
    combined_df = pd.concat([async_df, dynamic_df])

    # Save to CSV
    os.makedirs('/app/scrapers/data/dataframes', exist_ok=True)
    combined_df.to_csv('/app/scrapers/data/dataframes/political_articles.csv', index=False)
    print(combined_df.head())

if __name__ == "__main__":
    asyncio.run(main())