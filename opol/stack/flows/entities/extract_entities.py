import json
import logging
import re
import string
from typing import List, Tuple, Set

from redis import Redis
from prefect import flow, task
from redis.exceptions import RedisError

from core.models import Content
from core.utils import logger, UUIDEncoder, get_redis_url
from gliner import GLiNER

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EntityExtractor:
    def __init__(self, model_name: str = "EmergentMethods/gliner_medium_news-v2.1"):
        self.ner_tagger = self.load_model(model_name)
        logger.info("EntityExtractor initialized successfully.")

    @staticmethod
    def load_model(model_name: str) -> GLiNER:
        try:
            logger.info(f"Loading NER model: {model_name}")
            return GLiNER.from_pretrained(model_name)
        except Exception as e:
            logger.error(f"Failed to load NER model '{model_name}': {e}")
            raise

    @staticmethod
    def normalize_entity(text: str) -> str:
        """Normalize entity text by removing possessive endings."""
        return re.sub(r"’s$|\'s$", "", text).strip()

    @staticmethod
    def clean_text(text: str) -> str:
        """Remove unwanted characters and normalize whitespace."""
        text = text.translate(str.maketrans('', '', string.punctuation))
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    @task(log_prints=True)
    def predict_entities(self, text: str, labels: List[str]) -> List[Tuple[str, str]]:
        max_length = 512  # Adjust based on model's capabilities
        entities = []

        logger.debug(f"Starting NER prediction on text of length {len(text)}")

        for start in range(0, len(text), max_length):
            chunk = text[start:start + max_length]
            chunk_entities = self.ner_tagger.predict_entities(chunk, labels)
            logger.debug(f"Chunk {start//max_length + 1}: Extracted {len(chunk_entities)} entities.")
            entities.extend(chunk_entities)

        # Directly return all extracted entities without filtering
        all_entities = [
            (entity["text"], entity["label"])
            for entity in entities
        ]

        logger.debug(f"Total entities extracted: {len(all_entities)}")
        return all_entities

@task(retries=3, retry_delay_seconds=60, log_prints=True, cache_policy=None)
def retrieve_contents(batch_size: int) -> List[Content]:
    try:
        redis_conn = Redis.from_url(get_redis_url(), db=2, decode_responses=True)
        batch = redis_conn.lrange('contents_without_entities_queue', 0, batch_size - 1)
        if not batch:
            logger.info("No contents found in the queue.")
            return []
        redis_conn.ltrim('contents_without_entities_queue', batch_size, -1)
        contents = [Content(**json.loads(content)) for content in batch]
        logger.info(f"Retrieved {len(contents)} contents from Redis.")
        return contents
    except RedisError as e:
        logger.error(f"Redis error: {e}")
        return []
    finally:
        redis_conn.close()

@task(log_prints=True)
def process_content(content: Content, extractor: EntityExtractor) -> Tuple[Content, List[Tuple[str, str]], Set[str], List[str]]:
    title = extractor.clean_text(content.title) if content.title else ""
    text_content = extractor.clean_text(content.text_content) if content.text_content else ""
    full_text = f"{title}. {text_content}".strip()
    logger.debug(f"Processing Content ID: {content.id} with text length: {len(full_text)}")

    entities = extractor.predict_entities(full_text, labels=["person", "location", "geopolitical_entity", "organization"])
    logger.debug(f"Extracted Entities: {entities}")

    title_entities = extractor.predict_entities(title, labels=["location", "geopolitical_entity"]) if title else []
    logger.debug(f"Title Entities: {title_entities}")

    title_locations = {extractor.normalize_entity(text) for text, label in title_entities if label in {"location", "geopolitical_entity"}}
    title_entities_texts = [text for text, _ in title_entities]

    merged_entities = merge_entities(entities, extractor, title_entities_texts)
    logger.debug(f"Merged Entities: {merged_entities}")

    primary_locations, top_entities_texts = categorize_entities(merged_entities, title_locations)
    logger.debug(f"Primary Locations: {primary_locations}, Top Entities: {top_entities_texts}")

    return content, merged_entities, primary_locations, top_entities_texts

@task(log_prints=True)
def merge_entities(entities: List[Tuple[str, str]], extractor: EntityExtractor, title_entities_texts: List[str]) -> List[Tuple[str, str]]:
    entity_counts = {}
    for text, label in entities:
        normalized_text = extractor.normalize_entity(text)
        key = (normalized_text, label)
        entity_counts[key] = entity_counts.get(key, 0) + 1

    # Remove filtering conditions; include all entities
    merged_entities = [
        (entity, label) for (entity, label), count in entity_counts.items()
    ]
    logger.debug(f"Merged entities count: {len(merged_entities)}")
    return merged_entities

@task(log_prints=True)
def categorize_entities(merged_entities: List[Tuple[str, str]], title_locations: Set[str]) -> Tuple[Set[str], List[str]]:
    location_counts = {}
    entity_counts = {}

    for entity, label in merged_entities:
        if label in {"location", "geopolitical_entity"}:
            location_counts[entity] = location_counts.get(entity, 0) + 1
        entity_counts[entity] = entity_counts.get(entity, 0) + 1

    for loc in title_locations:
        location_counts[loc] = location_counts.get(loc, 0) + 10  # Boost title locations

    sorted_locations = sorted(location_counts.items(), key=lambda item: (item[0] in title_locations, item[1]), reverse=True)
    primary_locations = {loc for loc, _ in sorted_locations[:2]}

    top_entities = list(dict.fromkeys([
        entity for entity in title_locations if entity in entity_counts
    ]))
    additional_entities = [
        entity for entity, count in entity_counts.items()
        if count > 1 and entity not in top_entities
    ]
    top_entities.extend(sorted(additional_entities, key=lambda e: entity_counts[e], reverse=True)[:5 - len(top_entities)])
    logger.debug(f"Primary Locations: {primary_locations}, Top Entities: {top_entities}")
    return primary_locations, top_entities

@task(log_prints=True, cache_policy=None)
def push_entities(contents_with_entities: List[Tuple[Content, List[Tuple[str, str]], Set[str], List[str]]]):
    try:
        redis_conn = Redis.from_url(get_redis_url(), db=2, decode_responses=True)
        pipe = redis_conn.pipeline()
        for content, entities, primary_locations, top_entities_texts in contents_with_entities:
            content_data = content.model_dump()
            content_data.update({
                'entities': [{"text": text, "tag": label} for text, label in entities],
                'top_locations': list(primary_locations),
                'top_entities': top_entities_texts
            })
            pipe.lpush('contents_with_entities_queue', json.dumps(content_data, cls=UUIDEncoder))
            logger.info(f"Pushed Content ID {content.id} to Redis queue.")
        pipe.execute()
    except RedisError as e:
        logger.error(f"Redis error while pushing entities: {e}")
    finally:
        redis_conn.close()

@flow(log_prints=True)
def extract_entities_flow(batch_size: int = 50):
    logger.info("Starting entity extraction flow.")
    contents = retrieve_contents(batch_size=batch_size)
    if not contents:
        logger.info("No contents to process. Exiting flow.")
        return

    extractor = EntityExtractor()
    processed_contents = [process_content(content, extractor) for content in contents]
    logger.error(f"Processed contents: {processed_contents[:2]}")
    push_entities(processed_contents)
    logger.info("Entity extraction flow completed successfully.")

# if __name__ == "__main__":
#     extract_entities_flow.serve(
#         name="extract-entities-deployment",
#         cron="0/7 * * * *", # every 7 minutes
#         parameters={"batch_size": 20}
#     )