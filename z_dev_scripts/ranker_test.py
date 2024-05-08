import requests
import os
import FlagEmbedding

def call_vector(query):
    url = f"http://localhost:6969/search/?query={query}"
    response = requests.get(url)
    
    if response.status_code == 200:
        result = response.json()
        print(requests)
        return result
    else:
        console.print(f"[bold red]Failed to fetch data from the vector search API for query: {query}[/bold red]")
        return []

result = call_vector("politics")

print(result)
