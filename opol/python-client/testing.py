import asyncio
from opol.main import OPOL

opol = OPOL(mode="local")

# Print articles about "Sao Paulo"
articles_sao_paulo = opol.articles("Sao Paulo")
for article in articles_sao_paulo[:4]:
    print(
        f"Title: {article['title']}\n"
        f"Text: {article['text_content'][:80]}\n"
        f"Date: {article['insertion_date']}\n"
    )

# Print entities related to "Sao Paulo"
entities_sao_paulo = opol.entities.by_entity("Sao Paulo")
for entity in entities_sao_paulo[:4]:
    print(
        f"Entity: {entity['name']}\n"
        f"Type: {entity['type']}\n"
        f"Article Count: {entity['article_count']}\n"
        f"Total Frequency: {entity['total_frequency']}\n"
        f"Relevance Score: {entity['relevance_score']}\n"
    )

# Print articles about "Trump"
articles_trump = opol.articles("Trump")
for article in articles_trump[:2]:  # Only print the first two articles
    print(
        f"Title: {article['title']}\n"
        f"Text: {article['text_content'][:80]}\n"
        f"Date: {article['insertion_date']}\n"
    )

# Print geo events related to "War"
geo_events_war = opol.geo.json_by_event("War")
for feature in geo_events_war["features"]:
    print(feature)

# Print articles about "Trump"
articles_trump = opol.articles("Trump")
for article in articles_trump[:4]:
    print(f"Title: {article['title']}")

# Print entities related to "BBC"
entities_bbc = opol.entities.by_entity("Berlin")
for entity in entities_bbc[:2]:
    print(f"entity: {entity}")
