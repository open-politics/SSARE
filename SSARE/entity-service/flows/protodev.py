import json
import logging
import warnings  # Import the warnings module
import asyncio
import httpx
from typing import List, Tuple
from redis import Redis
from core.utils import logger, UUIDEncoder, get_redis_url
from core.models import Content
from gliner import GLiNER
import os
from rich.console import Console
from rich.table import Table
import re  # Import regex for normalization
from statistics import mean

# Suppress specific SQLAlchemy warnings
warnings.filterwarnings("ignore", message="relationship 'Content.entities' will copy column entity.id to column contententity.entity_id")

# Suppress warnings from the transformers package
logging.getLogger("transformers").setLevel(logging.ERROR)

# Global variable to store the NER model
ner_model = None

# Rich console setup
console = Console()

CLASSIFICATION_SERVICE_URL = "http://classification-service:5688/classify_dynamic"

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

def predict_ner_tags(text: str) -> List[Tuple[str, str]]:
    global ner_model
    if ner_model is None:
        ner_model = GLiNER.from_pretrained("EmergentMethods/gliner_medium_news-v2.1")
    
    labels = ["person", "location", "date", "event", "facility", "vehicle", "number", "organization"]
    
    max_length = 512  # Adjust this based on your model's capabilities and requirements
    entities = []
    
    # Process text in chunks manually
    for i in range(0, len(text), max_length):
        chunk = text[i:i + max_length]
        chunk_entities = ner_model.predict_entities(chunk, labels)
        entities.extend(chunk_entities)
    
    console.print(f"[DEBUG] All Extracted Entities: {entities}")
    
    filtered_entities = [
        (entity["text"], entity["label"]) 
        for entity in entities 
        if entity["label"] in ["person", "organization", "location"]
    ]
    
    console.print(f"[DEBUG] Filtered Entities: {filtered_entities}")
    return filtered_entities

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

# @task(log_prints=True)
def process_content(content: Content) -> Tuple[Content, List[Tuple[str, str]], List[Tuple[str, str]], set, List[str]]:
    full_text = ""
    if content.title:
        full_text += content.title + " "
    if content.text_content:
        full_text += content.text_content
    entities = predict_ner_tags(full_text.strip())
    
    # Automatically include locations from the title as top locations
    title_entities = predict_ner_tags(content.title.strip()) if content.title else []
    title_locations = {entity[0] for entity in title_entities if entity[1] in ['location']}
    title_entities_texts = [entity[0] for entity in title_entities]

    # Merge similar entities
    entities = merge_similar_entities(entities, title_entities_texts)
    
    # Count occurrences of location entities and all entities
    location_counts = {}
    entity_counts = {}
    for entity in entities:
        if entity[1] in ['location']:
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

    # Log top entities and top locations using rich
    entity_table = Table(title="Top Entities")
    entity_table.add_column("Entity", style="cyan")
    entity_table.add_column("Count", style="magenta")
    for entity_text in top_entities_texts:
        count = entity_counts.get(entity_text, 0)
        if count > 1 or entity_text in title_entities_texts:
            entity_table.add_row(entity_text, str(count))
    console.print(entity_table)

    location_table = Table(title="Top Locations")
    location_table.add_column("Location", style="green")
    for location in primary_locations:
        location_table.add_row(location)
    console.print(location_table)

    logger.info(f"Content title: {content.title}")
    headline_entities = predict_ner_tags(content.title.strip()) if content.title else []
    return (content, entities, headline_entities, primary_locations, top_entities_texts)

def push_contents_with_entities(contents_with_entities: List[Tuple[Content, List[Tuple[str, str]]]]):
    redis_conn = Redis.from_url(get_redis_url(), db=2, decode_responses=True)
    try:
        for content, entities, _, _ in contents_with_entities:
            entities_data = [{"text": entity[0], "label": entity[1]} for entity in entities]
            content_dict = content.dict()
            content_dict['entities'] = entities_data
            # redis_conn.lpush('contents_with_entities_queue', json.dumps(content_dict, cls=UUIDEncoder))
            logger.info(f"Content with entities prepared to push to queue: {content.url}")
    except Exception as e:
        logger.error(f"Error preparing contents with entities to queue: {str(e)}")
    finally:
        redis_conn.close()

async def send_classification_request(
    headline: str,
    top_entities: List[str],
    top_locations: List[str],
    request_type: str
) -> dict:
    # Define classification dimensions based on the request type
    if request_type == "integer":
        dimensions = [
            {
                "name": "is_extraction_good",
                "type": "integer",
                "description": "Rating of extraction quality"
            }
        ]
    elif request_type == "string":
        dimensions = [
            {
                "name": "explanation",
                "type": "string",
                "description": "Explanation for low extraction quality"
            }
        ]
    else:
        logger.error(f"Invalid request_type: {request_type}")
        return {}

    # Aggregate texts to classify with additional context
    texts = str(
        f"Headline: {headline}\n\n"
        f"Top Entities: {top_entities}\n\n"
        f"Locations: {top_locations}\n\n"
        "Context: The entities should be directly relevant to the headline. "
        "Please provide an explanation if the extraction quality is low, "
        "considering factors such as entity relevance, missing entities, "
        "or incorrect entity types."
    )

    payload = {
        "dimensions": dimensions,
        "texts": texts
    }

    console.print(f"[blue]Sending {request_type} classification request: {json.dumps(payload, indent=2)}[/blue]")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(CLASSIFICATION_SERVICE_URL, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            console.print(f"[blue]Received response from classification service: {json.dumps(data, indent=2)}[/blue]")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"Error sending {request_type} classification request: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return {}

async def send_to_classification_service(headline: str, top_entities: List[str], top_locations: List[str], request_type: str = "integer"):
    return await send_classification_request(headline, top_entities, top_locations, request_type)

async def extract_entities_flow(batch_size: int = 50, iterations: int = 20):
    logger.info("Starting entity extraction process")
    ratings = []
    outliers = []
    
    for i in range(1, iterations + 1):
        logger.info(f"--- Extraction Round {i} ---")
        contents = retrieve_contents_from_redis(batch_size)
        if contents:
            contents_with_entities = [process_content(content) for content in contents]
            headline = contents[0].title if contents[0].title else "No Headline"
            top_entities = contents_with_entities[0][4]
            top_locations = contents_with_entities[0][3]
            
            # Collect all entities and locations
            all_entities = list({entity for content in contents_with_entities for entity, _ in content[1]})
            all_locations = list({loc for content in contents_with_entities for loc in content[3]})
            
            # Send initial classification request and get rating
            data = await send_classification_request(headline, top_entities, top_locations, request_type="integer")
            rating = data.get("is_extraction_good", 0)
            ratings.append(rating)
            
            if rating < 7:
                # Send additional classification request for explanations
                explanation_data = await send_classification_request(headline, top_entities, top_locations, request_type="string")
                explanation = explanation_data.get("explanation", "No explanation provided.")
                outliers.append({
                    "round": i,
                    "headline": headline,
                    "rating": rating,
                    "explanation": explanation,
                    "top_entities": top_entities
                })
            else:
                outliers.append({
                    "round": i,
                    "headline": headline,
                    "rating": rating,
                    "explanation": "N/A",
                    "top_entities": all_entities
                })
        else:
            logger.info("No contents found in the queue.")
        
        await asyncio.sleep(1)  # Optional: wait between iterations
    
    logger.info("Entity extraction process completed")
    
    # Calculate average rating
    average_rating = mean(ratings) if ratings else 0
    
    # Log top entities
    logger.info(f"Top Entities: {all_entities}")
    
    # Display results using Rich
    table = Table(title="Entity Extraction Ratings")
    table.add_column("Run", style="cyan")
    table.add_column("Rating", style="magenta")
    table.add_column("Top Entities", style="yellow")
    
    for idx, rating in enumerate(ratings, 1):
        top_entities_str = ", ".join(all_entities)
        table.add_row(str(idx), str(rating), top_entities_str)
    
    table_avg = Table(title="Average Rating")
    table_avg.add_column("Average Rating", style="green")
    table_avg.add_row(str(round(average_rating, 2)))
    
    table_outliers = Table(title="Outliers (Ratings < 7)")
    table_outliers.add_column("Run", style="cyan")
    table_outliers.add_column("Headline", style="magenta")
    table_outliers.add_column("Rating", style="red")
    table_outliers.add_column("Explanation", style="yellow")
    table_outliers.add_column("Top Entities", style="yellow")
    
    for outlier in outliers:
        explanation = outlier["explanation"]
        top_entities_str = ", ".join(outlier["top_entities"])
        table_outliers.add_row(str(outlier["round"]), outlier["headline"], str(outlier["rating"]), explanation, top_entities_str)
    
    console.print(table)
    console.print(table_avg)
    console.print(table_outliers)
    
    return {"average_rating": average_rating, "outliers": outliers}

if __name__ == "__main__":
    asyncio.run(extract_entities_flow(batch_size=5, iterations=5))