import requests
from collections import Counter, defaultdict
import json

query = "USA"

def print_sorted_entities(x):
    url = 'http://136.243.80.175:5434/articles'
    params = {
        'geocoding_created': 0,
        'limit': 200,
        'embeddings_created': 1,
        'entities_extracted': 1,
        'search_text': query
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        for article in data:
            print(f"URL: {article['url']}")
            print(f"Headline: {article['headline']}")
            print(f"Paragraphs: {article['paragraphs']}")
            print("Entities:")
            entities = []
            for entity in article['entities']:
                entities.append(str(entity['tag']+';'+entity['text']))
                # print(f"{entity['text']},{entity['tag']}")
            print(entities[:20])
            print("---")
    else:
        print('API request failed.')

print_sorted_entities(10)