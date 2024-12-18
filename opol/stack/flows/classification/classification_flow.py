import asyncio
from typing import List
from redis.asyncio import Redis
from prefect import flow, task
from core.utils import UUIDEncoder, logger
from core.models import Content
from core.service_mapping import get_redis_url
from classification_models import ContentEvaluation, ContentRelevance
from xclass import XClass
from core.service_mapping import ServiceConfig
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.futures import wait
import json
import os

# Initialize config
config = ServiceConfig()

# Initialize ClassificationService
xclass = XClass()

@task(log_prints=True)
async def retrieve_contents_from_redis(batch_size: int) -> List[Content]:
    """Retrieve contents from Redis queue asynchronously."""
    redis_conn = await Redis.from_url(get_redis_url(), db=4)
    _contents = await redis_conn.lrange('contents_without_classification_queue', 0, batch_size - 1)
    await redis_conn.ltrim('contents_without_classification_queue', batch_size, -1)

    contents = []
    for content_data in _contents:
        try:
            content = Content(**json.loads(content_data))
            contents.append(content)
        except Exception as e:
            logger.error(f"Invalid content: {content_data}")
            logger.error(f"Error: {e}")

    logger.info(f"Successfully retrieved {len(contents)} contents")
    return contents

@task(log_prints=True)
async def classify_content(content: Content) -> dict:
    """Classify the content for relevance asynchronously."""
    try:
        user_text = f"Evaluate this article for relevance:\n\nHeadline: {content.title}\n\nContent: {content.text_content[:320]}"
        classification_result = xclass.classify(
            response_model=ContentRelevance,
            text=user_text
        )
        logger.debug(f"Model response: {classification_result}")
        return classification_result.model_dump()
    except Exception as e:
        logger.error(f"Error classifying content ID {content.id}: {e}")
        return {}

@task(log_prints=True)
async def evaluate_content(content: Content) -> ContentEvaluation:
    """Evaluate the content if it is relevant asynchronously."""
    try:
        user_text = f"Evaluate this article:\n\nHeadline: {content.title}\n\nContent: {content.text_content[:320]}"
        classification_result = xclass.classify(
            response_model=ContentEvaluation,
            text=user_text
        )
        return classification_result
    except Exception as e:
        logger.error(f"Error evaluating content ID {content.id}: {e}")
        return ContentEvaluation()

@task(log_prints=True)
async def write_contents_to_redis(serialized_contents):
    """Write serialized contents to Redis asynchronously."""
    if not serialized_contents:
        logger.info("No contents to write to Redis")
        return

    # Ensure each content is serialized to JSON
    serialized_contents = [json.dumps(content, cls=UUIDEncoder) for content in serialized_contents]

    redis_conn_processed = await Redis.from_url(get_redis_url(), db=4)
    await redis_conn_processed.lpush('contents_with_classification_queue', *serialized_contents)
    logger.info(f"Wrote {len(serialized_contents)} contents with classification to Redis")

@flow(task_runner=ThreadPoolTaskRunner(max_workers=50))
async def classify_contents_flow(batch_size: int):
    """Process a batch of contents: retrieve, classify, and store them asynchronously."""
    contents = await retrieve_contents_from_redis(batch_size=batch_size)

    if not contents:
        logger.warning("No contents to process.")
        return []

    futures = [classify_content.submit(content) for content in contents]
    # await wait(futures)  # Ensure all tasks are completed

    results = [future.result() for future in futures]  # Resolve futures
    evaluated_contents = []

    for content_dict, content in zip(results, contents):
        if not content_dict:
            continue
        if content_dict.get("type") != "Other":
            llm_evaluation = await evaluate_content(content)
            db_evaluation = ContentEvaluation(
                content_id=content.id,
                **llm_evaluation.model_dump()
            )

            content_dict_processed = {
                'url': content.url,
                'title': content.title,
                'evaluations': db_evaluation.model_dump(exclude={'id'})
            }
            evaluated_contents.append(content_dict_processed)
        else:
            logger.info(f"Content classified as irrelevant: {content.title[:50]}...")
            redis_conn = await Redis.from_url(get_redis_url(), db=4)
            await redis_conn.rpush('filtered_out_queue', json.dumps(content.model_dump(), cls=UUIDEncoder))

    if evaluated_contents:
        logger.info(f"Writing {len(evaluated_contents)} evaluated contents to Redis")
        await write_contents_to_redis(evaluated_contents)
    return evaluated_contents

async def process_content(content):
    """
    This function can be used for individual content processing if needed.
    """
    try:
        relevance = await classify_content(content)
        logger.info(f"Relevance result: {relevance}")
        if relevance.get("type") == "Other":
            logger.info(f"Content classified as irrelevant: {content.title[:50]}...")
            redis_conn = await Redis.from_url(get_redis_url(), db=4)
            await redis_conn.rpush('filtered_out_queue', json.dumps(content.model_dump(), cls=UUIDEncoder))
            return None
        else:
            llm_evaluation = await evaluate_content(content)
            logger.info(f"Evaluation completed for: {content.title[:50]}")
            
            db_evaluation = ContentEvaluation(
                content_id=content.id,
                **llm_evaluation.model_dump()
            )

            content_dict = {
                'url': content.url,
                'title': content.title,
                'evaluations': db_evaluation.model_dump(exclude={'id'})
            }
            return content_dict
    except Exception as e:
        logger.error(f"Error processing content: {content.title[:50]}...")
        logger.error(f"Error: {e}")
        return None

if __name__ == "__main__":
    asyncio.run(classify_contents_flow.serve(
        name="classify-contents-deployment",
        cron="*/10 * * * *", 
        parameters={"batch_size": 10}
    ))