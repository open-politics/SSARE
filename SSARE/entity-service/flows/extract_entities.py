import json
import logging
from typing import List, Tuple
from redis import Redis
from core.utils import logger, UUIDEncoder, get_redis_url
from core.models import Content
from prefect import task, flow
from flair.data import Sentence
from flair.models import SequenceTagger
from rich.console import Console
from rich.table import Table
import os
import re  # Import regex for normalization
from gliner import GLiNER

# Global variable to store the NER model
ner_tagger = None
console = Console()

@task(retries=3, retry_delay_seconds=60, log_prints=True, cache_policy=None)
def retrieve_contents_from_redis(batch_size: int) -> List[Content]:
    redis_conn = Redis.from_url(get_redis_url(), db=2, decode_responses=True)
    try:
        batch = redis_conn.lrange('contents_without_entities_queue', 0, batch_size - 1)
        redis_conn.ltrim('contents_without_entities_queue', batch_size, -1)
        return [Content(**json.loads(content)) for content in batch]
    finally:
        redis_conn.close()

def normalize_entity(text: str) -> str:
    """Normalize entity text by removing possessive endings."""
    return re.sub(r"’s$|\'s$", "", text).strip()

@task(log_prints=True)
def predict_ner_tags(text: str) -> List[Tuple[str, str]]:
    global ner_tagger
    if ner_tagger is None:
        ner_tagger = GLiNER.from_pretrained("EmergentMethods/gliner_medium_news-v2.1")
    
    labels = ["person", "location", "geopolitical_entity", "event", "organization"]
    
    max_length = 512  # Adjust this based on your model's capabilities and requirements
    entities = []
    
    # Process text in chunks manually
    for i in range(0, len(text), max_length):
        chunk = text[i:i + max_length]
        chunk_entities = ner_tagger.predict_entities(chunk, labels)
        entities.extend(chunk_entities)
    
    filtered_entities = [
        (entity["text"], entity["label"]) 
        for entity in entities 
        if entity["label"] in ["person", "geopolitical_entity", "organization"]
    ]
    
    return filtered_entities

@task(log_prints=True)
def merge_similar_entities(entities: List[Tuple[str, str]], title_entities_texts: List[str]) -> List[Tuple[str, str]]:
    merged_entities = {}
    for text, label in entities:
        normalized_text = normalize_entity(text)
        key = (normalized_text, label)
        if key in merged_entities:
            merged_entities[key] += 1
        else:
            merged_entities[key] = 1
    # Filter out entities that appear only once unless they're in the headline
    filtered_entities = [
        (entity, label) for (entity, label), count in merged_entities.items() 
        if count > 1 or entity in title_entities_texts
    ]
    return filtered_entities

@task(log_prints=True)
def process_content(content: Content) -> Tuple[Content, List[Tuple[str, str]], set, List[str]]:
    full_text = ""
    if content.title:
        full_text += content.title + " "
    if content.text_content:
        full_text += content.text_content
    entities = predict_ner_tags(full_text.strip())
    
    # Automatically include locations from the title as top locations
    title_entities = predict_ner_tags(content.title.strip()) if content.title else []
    title_locations = {entity[0] for entity in title_entities if entity[1] in ['location', 'geopolitical_entity']}
    title_entities_texts = [entity[0] for entity in title_entities]

    # Merge similar entities
    entities = merge_similar_entities(entities, title_entities_texts)
    
    # Count occurrences of location entities and all entities
    location_counts = {}
    entity_counts = {}
    for entity in entities:
        if entity[1] in ['location', 'geopolitical_entity']:
            location_counts[entity[0]] = location_counts.get(entity[0], 0) + 1
        # Count all entities for top_entities
        entity_counts[entity[0]] = entity_counts.get(entity[0], 0) + 1
    
    # Ensure title locations are included in location counts with higher priority
    for loc in title_locations:
        location_counts[loc] = location_counts.get(loc, 0) + 10  # Adding a weight of 10 for title locations

    # Sort locations by count and prioritize those in the title
    top_locations_sorted = sorted(location_counts.items(), key=lambda item: (item[0] in title_locations, item[1]), reverse=True)
    primary_locations = set()
    for loc, _ in top_locations_sorted:
        if loc in title_locations:
            primary_locations.add(loc)
    for loc, _ in top_locations_sorted:
        if len(primary_locations) < 2:
            primary_locations.add(loc)
        else:
            break

    # Identify top entities (e.g., top 5), prioritizing title entities
    top_entities = [entity for entity in title_entities_texts if entity in entity_counts]
    # Add entities that have a count greater than 1
    additional_top_entities = [
        entity for entity, count in entity_counts.items() 
        if count > 1 and entity not in top_entities
    ]
    top_entities.extend(sorted(additional_top_entities, key=lambda e: entity_counts[e], reverse=True)[:5 - len(top_entities)])

    # Remove duplicates and ensure entities exist in entity_counts
    top_entities_texts = list(dict.fromkeys(top_entities))  # Preserves order and removes duplicates

    return (content, entities, primary_locations, top_entities_texts)

@task(log_prints=True, cache_policy=None)
def push_contents_with_entities(contents_with_entities: List[Tuple[Content, List[Tuple[str, str]], set, List[str]]]):
    redis_conn = Redis.from_url(get_redis_url(), db=2, decode_responses=True)
    try:
        for content, entities, primary_locations, top_entities_texts in contents_with_entities:
            entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
            content_dict = content.dict()
            content_dict['entities'] = entities_data
            content_dict['top_locations'] = list(primary_locations)
            content_dict['top_entities'] = top_entities_texts
            redis_conn.lpush('contents_with_entities_queue', json.dumps(content_dict, cls=UUIDEncoder))
            logger.info(f"Content with entities pushed to queue: {content.url}")
    except Exception as e:
        logger.error(f"Error pushing contents with entities to queue: {str(e)}")
    finally:
        redis_conn.close()

@flow(log_prints=True)
def extract_entities_flow(batch_size: int = 50):
    logger.info("Starting entity extraction process")
    contents = retrieve_contents_from_redis(batch_size=batch_size)
    if contents:
        # futures = [process_content(content) for content in contents]
        # contents_with_entities = [future.result() for future in futures]
        
        contents_with_entities = [process_content(content) for content in contents]
        push_contents_with_entities(contents_with_entities)

        # Rich log the headlines, top entities, and locations
        table = Table(title="Entity Extraction Results")
        table.add_column("Headline", style="cyan")
        table.add_column("Top Entities", style="magenta")
        table.add_column("Primary Locations", style="yellow")
        
        for content, _, primary_locations, top_entities_texts in contents_with_entities:
            headline = content.title if content.title else "No Title"
            top_entities_str = ", ".join(top_entities_texts)
            primary_locations_str = ", ".join(primary_locations)
            table.add_row(headline, top_entities_str, primary_locations_str)
        
        console.print(table)
        
        logger.info(f"Entities extracted for {len(contents)} contents.")
    else:
        logger.info("No contents found in the queue.")
    logger.info("Entity extraction process completed")
    return {"message": "Entity extraction completed"}

if __name__ == "__main__":
    extract_entities_flow.serve(
        name="extract-entities-deployment",
        cron="0/7 * * * *", # every 7 minutes
        parameters={"batch_size": 50}
    )