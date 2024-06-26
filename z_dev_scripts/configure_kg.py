import json, requests
from collections import defaultdict, Counter
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

console = Console()

with open('response.json', 'r') as f:
    response = json.load(f)

def
all_entities = []
for item in tqdm(response['results'], desc="Processing articles"):
    combined = f"{item['title']} {item['content']}"
    entities = requests.get('http://localhost:1290/fetch_entities', params={'text': combined}).json()['entities']
    all_entities.extend(sorted(entities, key=lambda x: x['tag']))

# Sort all entities by tag
sorted_entities = sorted(all_entities, key=lambda x: x['tag'])

# Count most relevant entities for each type
entity_counter = defaultdict(Counter)
for entity in all_entities:
    entity_counter[entity['tag']][entity['text']] += 1

# Print most relevant entities for each type
for tag, counter in entity_counter.items():
    table = Table(title=f"Most relevant entities for {tag}")
    table.add_column("Entity", justify="left", style="red", no_wrap=True)
    table.add_column("Count", justify="right", style="blue")
    for entity, count in counter.most_common(8):  # Adjust the number to get more or fewer top entities
        table.add_row(entity, str(count))
    console.print(table)


