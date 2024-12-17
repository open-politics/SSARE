import requests

def get_entity_data(entity):
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "format": "json",
        "titles": entity,
        "prop": "extracts|links|categories|sections",
        "exintro": True,
        "explaintext": True,
        "pllimit": "max",
        "cllimit": "max",
        "sllimit": "max"
    }
    response = requests.get(url, params=params)
    data = response.json()
    pages = data['query']['pages']
    for page_id, page_data in pages.items():
        if 'extract' in page_data:
            entity_info = {
                "extract": page_data.get('extract', 'No extract available'),
                "links": [link['title'] for link in page_data.get('links', [])],
                "categories": [category['title'] for category in page_data.get('categories', [])],
                "sections": [section['line'] for section in page_data.get('sections', [])]
            }
            return entity_info
    return None

def main():
    entities = ["France", "Germany", "Italy", "Spain", "Portugal"]
    entity_data = {}
    for entity in entities:
        data = get_entity_data(entity)
        if data:
            entity_data[entity] = data
        else:
            entity_data[entity] = "No data found"
    
    for entity, data in entity_data.items():
        print(f"Data for {entity}:\n{data}\n")

if __name__ == "__main__":
    main()
