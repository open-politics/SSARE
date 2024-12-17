import requests
import re
from FlagEmbedding import FlagReranker
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

reranker = FlagReranker('BAAI/bge-reranker-v2-m3', use_fp16=True)
console = Console()

def clean_text(text):
    # Remove extra whitespace
    return text.strip()

def call_vector(query):
    url = f"http://localhost:6969/search/?query={query}"
    response = requests.get(url)
    
    if response.status_code == 200:
        result = response.json()
        return result
    else:
        console.print(f"[bold red]Failed to fetch data from the vector search API for query: {query}[/bold red]")
        return []

# Main execution flow
if __name__ == "__main__":
    query = "Populism in Europe"
    
    console.print(Panel(f"[bold]Processing query:[/bold] {query}", expand=False))
    
    vector_result = call_vector(query)
    
    if vector_result:
        # Extract the article headlines and scores from the vector search result
        article_data = []
        for article in vector_result:
            if 'payload' in article and 'headline' in article['payload']:
                article_data.append((article['payload']['headline'], article['score']))
            
        if article_data:
            # Compute relevance scores for the article headlines using the reranker
            reranker_scores = [reranker.compute_score([(query, headline)], normalize=True) for headline, _ in article_data]

            # Combine the article headlines, original scores, and reranker scores into a list of tuples
            ranked_articles = [(headline, original_score, reranker_score) for (headline, original_score), reranker_score in zip(article_data, reranker_scores)]

            # Sort the ranked articles based on the weighted scores in descending order
            ranked_articles.sort(key=lambda x: x[1] * x[2], reverse=True)

            # Print the top 5 ranked articles, their original scores, reranker scores, and the first 100 characters of the article text
            console.print(Panel(f"[bold]Top 5 ranked articles for query '{query}':[/bold]", expand=False))
            for i, (article, original_score, reranker_score) in enumerate(ranked_articles[:5], start=1):
                article_text = next((a['payload']['paragraphs'] for a in vector_result if a['payload']['headline'] == article), '')
                article_text = re.sub(r'\s+', ' ', article_text)  # Remove extra whitespace
                console.print(f"[bold]{i}. {article}[/bold] (Original Score: {original_score:.4f}, Reranker Score: {reranker_score:.4f})")
                console.print(f"   {article_text[:100].strip()}...")
                print()  # Add a blank line for separation

            # Print the range of weighted scores
            weighted_scores = [original_score * reranker_score for _, original_score, reranker_score in ranked_articles]
            min_score = min(weighted_scores)
            max_score = max(weighted_scores)
            console.print(f"[bold]Weighted Score Range:[/bold] {min_score:.4f} - {max_score:.4f}")
        else:
            console.print(f"[bold yellow]No valid headlines found in the vector search result for query '{query}'[/bold yellow]")
    else:
        console.print(f"[bold yellow]No articles found in the vector search result for query '{query}'[/bold yellow]")