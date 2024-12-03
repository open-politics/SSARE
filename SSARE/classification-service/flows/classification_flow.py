import asyncio
from typing import List
from redis.asyncio import Redis
from prefect import flow, task
from core.utils import UUIDEncoder, logger
from core.models import Content
from core.service_mapping import get_redis_url
from classification_models import ContentEvaluation, ContentRelevance
from classx import classify_with_model
from core.service_mapping import ServiceConfig
from prefect.task_runners import ThreadPoolTaskRunner
from prefect.futures import wait

import json
import os
from uuid import UUID

# Define the model to use
model = "gemini-1.5-flash-latest"
config = ServiceConfig()  # Initialize config

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
    """Classify the content using LLM for relevance asynchronously."""
    response = classify_with_model(
        content=content,
        response_model=ContentRelevance,
        system_prompt="You are an AI assistant that analyzes articles for relevance.",
        user_content=f"Evaluate this article for relevance:\n\nHeadline: {content.title}\n\nContent: {content.text_content[:320]}"
    )
    logger.debug(f"Model response: {response}")
    return response.dict()  # Convert to dictionary for serialization

@task(log_prints=True)
async def evaluate_content(content: Content) -> ContentEvaluation:
    """Evaluate the content using LLM if it is relevant asynchronously."""
    response = classify_with_model(
        content=content,
        response_model=ContentEvaluation,
        system_prompt="You are an AI assistant that provides comprehensive evaluations.",
        user_content=f"Evaluate this article:\n\nHeadline: {content.title}\n\nContent: {content.text_content[:320]}"
    )
    return response

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
    wait(futures)  # Ensure all tasks are completed

    results = [future.result() for future in futures]  # Resolve futures
    evaluated_contents = [content for content in results if content]

    if evaluated_contents:
        logger.info(f"Writing {len(evaluated_contents)} evaluated contents to Redis")
        await write_contents_to_redis(evaluated_contents)
    return evaluated_contents

async def process_content(content):
    try:
        relevance = await classify_content(content)
        logger.info(f"Relevance result: {relevance}")
        if relevance.type == "Other":
            logger.info(f"Content classified as irrelevant: {content.title[:50]}...")
            redis_conn = await Redis.from_url(get_redis_url(), db=4)
            await redis_conn.rpush('filtered_out_queue', json.dumps(content.dict(), cls=UUIDEncoder))
            return None
        else:
            llm_evaluation = await evaluate_content(content)
            logger.info(f"Evaluation completed for: {content.title[:50]}")
            
            db_evaluation = ContentEvaluation(
                content_id=content.id,
                **llm_evaluation.dict()
            )

            content_dict = {
                'url': content.url,
                'title': content.title,
                'evaluations': db_evaluation.dict(exclude={'id'})
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
        parameters={"batch_size": 100}
    ))
