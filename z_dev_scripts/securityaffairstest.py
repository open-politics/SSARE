import os
import newspaper
from bs4 import BeautifulSoup
import requests
import pandas as pd

CATEGORY_FILE = 'categories.txt'
CSV_FILE = 'articles.csv'

def get_categories():
    if os.path.exists(CATEGORY_FILE):
        with open(CATEGORY_FILE, 'r') as file:
            return [line.strip() for line in file.readlines()]
    else:
        # Build the newspaper source to find categories
        securityaffairs = newspaper.build('https://securityaffairs.com/', number_threads=3)
        categories = [category.url for category in securityaffairs.categories]
        with open(CATEGORY_FILE, 'w') as file:
            for category in categories:
                file.write(f"{category}\n")
        return categories

# Define the categories to use
selected_categories = [
    'https://securityaffairs.com/category/cyber-crime',
    'https://securityaffairs.com/category/hacking',
    'https://securityaffairs.com/category/malware'
]

# Find all article URLs in the selected categories
article_urls = []
for category_url in selected_categories:
    response = requests.get(category_url)
    soup = BeautifulSoup(response.content, 'html.parser')
    links = soup.find_all('a', href=True)
    for link in links:
        url = link['href']
        if url.startswith('https://securityaffairs.com/'):
            article_urls.append(url)

# Use the newspaper Article method on the found links
articles = []
for url in article_urls:
    article = newspaper.Article(url)
    article.download()
    article.parse()
    articles.append({
        "url": url,
        "title": article.title,
        "text": article.text,
        "authors": article.authors,
        "publish_date": article.publish_date,
        "top_image": article.top_image,
        "videos": article.movies
    })

# Save articles to a CSV file
df = pd.DataFrame(articles)
df.to_csv(CSV_FILE, index=False)

print(f"Saved {len(articles)} articles to {CSV_FILE}")