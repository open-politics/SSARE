import httpx

url = "http://localhost:0420/generate_query_embeddings"
payload = {"query": "Your test query here"}
response = httpx.post(url, json=payload)

print(response.json())
