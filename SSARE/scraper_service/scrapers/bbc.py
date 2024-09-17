from playwright.sync_api import Playwright, sync_playwright, expect
from urllib.parse import urljoin
import pandas as pd
import os
from newspaper import Article

def scrape_articles(page, base_url, visited_urls, max_depth, current_depth=0):
    if current_depth >= max_depth:
        return []
    
    links = page.query_selector_all('a')
    article_urls = []
    
    for link in links:
        href = link.get_attribute('href')
        if href and ("news/world" in href or "politics" in href):
            absolute_url = urljoin(base_url, href)
            if absolute_url not in visited_urls:
                visited_urls.add(absolute_url)
                article_urls.append(absolute_url)
    
    data = []
    for url in article_urls:
        print(url)
        article = Article(url)
        article.download()
        article.parse()
        
        paragraphs = article.text if article.text else ""
        data.append({
            "url": url,
            "headline": article.title,
            "paragraphs": paragraphs,
            "source": "BBC News"
        })
        
        data += scrape_articles(page, url, visited_urls, max_depth, current_depth + 1)
    
    return data

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    base_url = "https://www.bbc.com"
    page.goto(base_url + "/news")
    
    visited_urls = set()
    max_depth = 1  # Adjust the depth as needed
    data = scrape_articles(page, base_url, visited_urls, max_depth)
    
    context.close()
    browser.close()
    
    # Create a DataFrame from the scraped data
    df = pd.DataFrame(data)
    
    # Print the DataFrame
    print(df)
    
    # Create the directory if it doesn't exist
    os.makedirs('/app/scrapers/data/dataframes', exist_ok=True)

    file_path = '/app/scrapers/data/dataframes/bbc_articles.csv'
    df.to_csv(file_path, index=False)

with sync_playwright() as playwright:
    run(playwright)