import json
import logging
from typing import List, Tuple
from redis import Redis
from core.utils import logger, UUIDEncoder, get_redis_url
from core.models import Content
from prefect import task, flow
from flair.data import Sentence
from flair.models import SequenceTagger
from prefect_ray import RayTaskRunner
import os

# Global variable to store the NER model
ner_tagger = None

@task(retries=3, retry_delay_seconds=60, log_prints=True, cache_policy=None)
def retrieve_contents_from_redis(batch_size: int) -> List[Content]:
    redis_conn = Redis.from_url(get_redis_url(), db=2, decode_responses=True)
    try:
        batch = redis_conn.lrange('contents_without_entities_queue', 0, batch_size - 1)
        redis_conn.ltrim('contents_without_entities_queue', batch_size, -1)
        return [Content(**json.loads(content)) for content in batch]
    finally:
        redis_conn.close()

@task(log_prints=True)
def predict_ner_tags(text: str) -> List[Tuple[str, str]]:
    global ner_tagger
    if ner_tagger is None:
        ner_tagger = SequenceTagger.load("flair/ner-english-fast")
    
    sentence = Sentence(text)
    ner_tagger.predict(sentence)
    return [(entity.text, entity.tag) for entity in sentence.get_spans('ner')]

@task(log_prints=True)
def process_content(content: Content) -> Tuple[Content, List[Tuple[str, str]]]:
    text = ""
    if content.title:
        text += content.title + " "
    if content.text_content:
        text += content.text_content
    entities = predict_ner_tags(text.strip())
    return (content, entities)

@task(log_prints=True, cache_policy=None)
def push_contents_with_entities(contents_with_entities: List[Tuple[Content, List[Tuple[str, str]]]]):
    redis_conn = Redis.from_url(get_redis_url(), db=2, decode_responses=True)
    try:
        for content, entities in contents_with_entities:
            entities_data = [{"text": entity[0], "tag": entity[1]} for entity in entities]
            content_dict = content.dict()
            content_dict['entities'] = entities_data
            redis_conn.lpush('contents_with_entities_queue', json.dumps(content_dict, cls=UUIDEncoder))
            logger.info(f"Content with entities pushed to queue: {content.url}")
    except Exception as e:
        logger.error(f"Error pushing contents with entities to queue: {str(e)}")
    finally:
        redis_conn.close()

@flow(task_runner=RayTaskRunner(address=os.getenv("RAY_ADDRESS"), init_kwargs={"runtime_env":{"pip": ["flair", "redis", "prefect"]}}), log_prints=True)
def extract_entities_flow(batch_size: int = 50):
    logger.info("Starting entity extraction process")
    contents = retrieve_contents_from_redis(batch_size)
    if contents:
        futures = [process_content.submit(content) for content in contents]
        contents_with_entities = [future.result() for future in futures]
        push_contents_with_entities(contents_with_entities)
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