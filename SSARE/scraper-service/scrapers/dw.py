from .base_scraper import BaseScraper
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from newspaper import Article
import asyncio



class DWScraper(BaseScraper):
    source_name = "DW"
    start_url = "https://www.dw.com/en/"

    async def parse(self, html: str) -> list:
        soup = BeautifulSoup(html, features="html.parser")
        all_urls = [a['href'] for a in soup.find_all('a', href=True) if a['href'].startswith('/en/')]
        full_urls = [url if url.startswith('http') else urljoin(self.start_url, url) for url in all_urls]
        article_urls = list(set(full_urls))  # Remove duplicates
        self.logger.info(f"Found {len(article_urls)} unique DW article URLs.")
        return article_urls

    def url_is_article(self, url: str) -> bool:
        parsed_url = urlparse(url)
        path_segments = parsed_url.path.strip("/").split("/")
        # DW article URLs typically have '/en/category/article-name'
        return len(path_segments) > 2

    async def process_article(self, session, url: str) -> dict:
        try:
            self.logger.debug(f"Starting to process article at {url}")
            article = Article(url)
            await asyncio.to_thread(article.download)
            await asyncio.to_thread(article.parse)

            if len(article.text) < 100:
                self.logger.warning(f"Skipping short article at {url}")
                return None

            headline = article.title or article.text[:30] + "..."
            top_image = article.top_image if "placeholder" not in article.top_image else None
            images = [img for img in article.images if "placeholder" not in img]
            publish_date = article.publish_date.isoformat() if article.publish_date else None

            self.logger.info(f"Processed article at {url}")

            return {
                "url": url,
                "title": headline,
                "text_content": article.text,
                "top_image": top_image,
                "images": images,
                "publication_date": publish_date,
                "summary": article.summary,
                "meta_summary": article.meta_description,
                "source": self.source_name
            }
        except Exception as e:
            self.logger.error(f"Error processing article at {url}: {e}")
            return None