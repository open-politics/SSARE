from .base_scraper import BaseScraper
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

class CNNScraper(BaseScraper):
    source_name = "CNN"
    start_url = "https://www.cnn.com"

    async def parse(self, html: str) -> list:
        soup = BeautifulSoup(html, features="html.parser")
        all_urls = [urljoin(self.start_url, a['href']) for a in soup.find_all('a', href=True)
                    if a['href']]
        # Remove duplicates
        all_urls = list(set(all_urls))
        article_urls = [url for url in all_urls if self.url_is_article(url)]
        self.logger.info(f"Found {len(article_urls)} CNN article URLs.")
        return article_urls

    def url_is_article(self, url: str) -> bool:
        parsed_url = urlparse(url)
        path_segments = parsed_url.path.strip("/").split("/")

        # CNN article URLs typically have '/year/month/day/category/article-name'
        if len(path_segments) >= 5:
            year, month, day = path_segments[:3]
            if year.isdigit() and month.isdigit() and day.isdigit():
                return True
        return False