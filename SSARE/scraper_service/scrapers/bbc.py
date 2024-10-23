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
        if href and (
            "/news" in href or 
            "/articles" in href or
            "/topics" in href or
            any(region in href for region in [
                "/africa", "/asia", "/australia", 
                "/europe", "/latin_america", "/middle_east"
            ])
        ) and "/sport" not in href:  # Exclude sport articles
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
        headline = article.title
        
        # Skip articles that start with Copyright
        if paragraphs.startswith("Copyright"):
            continue
            
        # Use first 30 chars of paragraphs if headline is "BBC News"
        if headline == "BBC News":
            headline = paragraphs[:30] + "..." if len(paragraphs) > 30 else paragraphs
        # Use first 20 chars of paragraphs if headline is "Latest News & Updates"
        elif headline == "Latest News & Updates":
            headline = paragraphs[:20] + "..." if len(paragraphs) > 20 else paragraphs
            
        data.append({
            "url": url,
            "headline": headline,
            "paragraphs": paragraphs,
            "source": "BBC News"
        })
        
        data += scrape_articles(page, url, visited_urls, max_depth, current_depth + 1)
    
    return data

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    
    # Start URLs
    start_urls = [
        "https://www.bbc.com/news",
        "https://www.bbc.com/news/politics"
    ]
    
    visited_urls = set()
    max_depth = 1
    all_data = []
    
    for start_url in start_urls:
        page.goto(start_url)
        data = scrape_articles(page, "https://www.bbc.com", visited_urls, max_depth)
        all_data.extend(data)
    
    context.close()
    browser.close()
    
    # Create a DataFrame from the scraped data
    df = pd.DataFrame(all_data)
    
    # Print the DataFrame
    print(df)
    
    # Create the directory if it doesn't exist
    os.makedirs('/app/scrapers/data/dataframes', exist_ok=True)

    file_path = '/app/scrapers/data/dataframes/bbc_articles.csv'
    df.to_csv(file_path, index=False)

with sync_playwright() as playwright:
    run(playwright)
