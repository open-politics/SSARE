from typing import Dict, List, Tuple
from .client_base import BaseClient
import numpy as np

class Embeddings(BaseClient):
    """
    Client to interact with the Embeddings API endpoints.
    """
    def __init__(self, mode: str, api_key: str = None, timeout: int = 60):
        super().__init__(mode, api_key=api_key, timeout=timeout, service_name="service-embeddings", port=420)
    
    def __call__(self, *args, **kwargs):
        return self.get_embeddings(*args, **kwargs)
    
    def get_embeddings(self, text: str) -> dict:
        endpoint = f"/generate_query_embeddings"
        params = {"query": text}
        response = self.get(endpoint, params)
        embeddings = response.get("embeddings", [])
        return embeddings
    
    def cosine(self, a, b):
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    def rerank_articles(self, query_embedding: List[float], articles: List[Dict], text_field: str = "title") -> List[Tuple[Dict, float]]:
        """
        Reranks articles based on the cosine similarity of their embeddings to the query embedding.

        Args:
            query_embedding (List[float]): The embedding of the query.
            articles (List[Dict]): List of articles to rerank.
            text_field (str): The article field to embed ('title', 'content', or 'both').

        Returns:
            List[Tuple[Dict, float]]: Sorted list of tuples containing articles and their similarity scores.
        """
        if text_field == "title":
            texts = [article.title for article in articles]
        elif text_field == "content":
            texts = [article.content[:300] for article in articles]
        elif text_field == "both":
            texts = [f"{article.title}\n{article.content[:300]}" for article in articles]
        else:
            raise ValueError("Invalid text_field value. Choose 'title', 'content', or 'both'.")

        article_embeddings = [self.get_embeddings(text) for text in texts]

        ranked_articles = sorted(
            ((article, self.cosine(query_embedding, embedding)) for article, embedding in zip(articles, article_embeddings)),
            key=lambda x: x[1],
            reverse=True
        )
        return ranked_articles



