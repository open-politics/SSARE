from .base_scraper import BaseScraper
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import asyncio
from newspaper import Article

class BBCScraper(BaseScraper):
    source_name = "BBC News"
    start_url = "https://www.bbc.com/news"

    async def parse(self, html: str) -> list:
        soup = BeautifulSoup(html, features="html.parser")
        links = soup.find_all('a', href=True)
        article_urls = []

        for link in links:
            href = link['href']
            if href and (
                "/news" in href or 
                "/articles" in href or
                "/topics" in href or
                "/in_pictures" in href or
                any(region in href for region in [
                    "/africa", "/asia", "/australia", 
                    "/europe", "/latin_america", "/middle_east",
                    "/us-canada", "/uk"
                ])
            ) and not any(excluded in href for excluded in [
                "/sport", 
                "/weather",
                "/radio",
                "/sounds",
                "/worklife",
                "/future",
                "/culture",
                "/travel",
                "/tv",
                "/iplayer",
                "/bitesize",
                "/food",
                "/live",
                "/bbcindepth",
                "/reality_check"
            ]):
                absolute_url = urljoin(self.start_url, href)
                article_urls.append(absolute_url)

        article_urls = list(set(article_urls))  # Remove duplicates
        self.logger.info(f"Found {len(article_urls)} BBC article URLs.")
        return article_urls

    async def process_article(self, session, url: str) -> dict:
        try:
            self.logger.debug(f"Starting to process article at {url}")
            article = Article(url)
            await asyncio.to_thread(article.download)
            await asyncio.to_thread(article.parse)

            if article.text.startswith("Copyright") or len(article.text) < 100:
                self.logger.warning(f"Skipping article at {url} due to copyright or short length")
                return None

            headline = article.title
            if headline == "BBC News":
                headline = article.text[:30] + "..." if len(article.text) > 30 else article.text
            elif headline == "Latest News & Updates":
                headline = article.text[:20] + "..." if len(article.text) > 20 else article.text

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
                "authors": article.authors,
                "publish_date": publish_date,
                "summary": article.summary,
                "meta_summary": article.meta_description,
                "source": self.source_name
            }
        except Exception as e:
            self.logger.error(f"Error processing article at {url}: {e}")
            return None