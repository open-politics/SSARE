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
        return []

result = call_vector("politics")

print(result)
