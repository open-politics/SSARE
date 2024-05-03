import requests
from collections import Counter, defaultdict
import json

def print_sorted_gpe_entities(x):
    url = 'http://136.243.80.175:5434/articles'
    params = {
        'geocoding_created': 0,
        'limit': 200,
        'embeddings_created': 1,
        'entities_extracted': 1
    }

    entity_type = 'NORP'

    # Just for Navigation
    tag_meaning = {
        'CARDINAL': 'cardinal value',
        'DATE': 'date value',
        'EVENT': 'event name',
        'FAC': 'building name',
        'GPE': 'geo-political entity',
        'LANGUAGE': 'language name',
        'LAW': 'law name',
        'LOC': 'location name',
        'MONEY': 'money name',
        'NORP': 'affiliation',
        'ORDINAL': 'ordinal value',
        'ORG': 'organization name',
        'PERCENT': 'percent value',
        'PERSON': 'person name',
        'PRODUCT': 'product name',
        'QUANTITY': 'quantity value',
        'TIME': 'time value',
        'WORK_OF_ART': ''
    }

    tag_meaning_json = json.dumps(tag_meaning)
    print(tag_meaning_json)

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        
        # Create a dictionary to count GPE entities and track articles
        gpe_counter = Counter()
        gpe_articles = defaultdict(list)
        
        # Loop through articles, count GPE entities and link entities to articles
        for article in data:
            entities = article['entities']
            for entity in entities:
                if entity['tag'] == entity_type:  # Check if the entity is a Geopolitical Entity
                    entity_name = entity['text']
                    gpe_counter[entity_name] += 1
                    if article['headline']:
                        gpe_articles[entity_name].append(article['headline'])
                    else:
                        gpe_articles[entity_name].append(article['url'])
        
        # Sort GPE entities by frequency
        sorted_gpes = gpe_counter.most_common(x)
        
        # Reverse for better readability
        sorted_gpes = list(reversed(sorted_gpes))

        # Print GPE entities and associated articles
        for gpe, count in sorted_gpes:
            print(f"{entity_type}: {gpe}, Count: {count}")
            print("Associated Articles:")
            for article in set(gpe_articles[gpe]):  # Using set to avoid duplicates
                print(f" - {article}")
            print("\n")
    else:
        print('API request failed.')

print_sorted_gpe_entities(10)
