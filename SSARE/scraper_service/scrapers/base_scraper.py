import asyncio
from newspaper import Article
import pandas as pd
from aiohttp import ClientSession
from prefect import get_run_logger

class BaseScraper:
    source_name = "Base"

    def __init__(self):
        self.logger = get_run_logger()

    async def fetch(self, session: ClientSession, url: str) -> str:
        try:
            async with session.get(url) as response:
                self.logger.debug(f"Fetching URL: {url}")
                return await response.text()
        except Exception as e:
            self.logger.error(f"Error fetching URL {url}: {e}")
            return ""

    async def parse(self, html: str) -> list:
        """Override this method in subclasses."""
        return []

    async def scrape(self) -> pd.DataFrame:
        async with ClientSession() as session:
            html = await self.fetch(session, self.start_url)
            if not html:
                self.logger.error(f"No HTML content fetched from {self.start_url}")
                return pd.DataFrame()
            article_urls = await self.parse(html)
            articles = await self.process_articles(session, article_urls)
            df = pd.DataFrame(articles)
            return df

    async def process_articles(self, session: ClientSession, urls: list) -> list:
        tasks = [self.process_article(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
        articles = [article for article in results if article]
        return articles

    async def process_article(self, session: ClientSession, url: str) -> dict:
        try:
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