from typing import List, Union
import os
import json
import numpy as np
import nltk
import asyncio

from prefect import flow, task, runtime
from prefect.logging import get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from redis import Redis
from fastembed import TextEmbedding

from core.models import Content
from core.utils import get_redis_url

nltk.download('punkt')

# Constants
SIMILARITY_THRESHOLD = 0.5
MAX_CHUNK_SIZE = 1000

# Global variable to store the model
model = None

def get_model():
    """
    Returns a singleton instance of the SentenceTransformer model.
    """
    if not hasattr(runtime.flow_run, 'model'):
        token = os.getenv("HUGGINGFACE_TOKEN")
        embedding_model = TextEmbedding(model="jinaai/jina-embeddings-v2-base-de")
        runtime.flow_run.model = embedding_model
    return runtime.flow_run.model

def encode_text(texts: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
    """
    Encodes a single text string or a list of text strings into embeddings.
    """
    model = get_model()
    embeddings_generator = model.embed(texts)
    embeddings_list = [embedding.tolist() for embedding in embeddings_generator]
    return embeddings_list[0]

def semantic_chunking(text: str) -> List[str]:
    """
    Splits the input text into semantically coherent chunks.
    """
    sentences = nltk.sent_tokenize(text, language='english')
    sentence_embeddings = encode_text(sentences)

    chunks = []
    current_chunk = []
    current_chunk_embeddings = []

    for i, sentence in enumerate(sentences):
        current_chunk.append(sentence)
        current_chunk_embeddings.append(sentence_embeddings[i])

        if len(current_chunk_embeddings) > 1:
            vec_a = current_chunk_embeddings[-1]
            vec_b = current_chunk_embeddings[-2]
            cos_sim = np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))

            if cos_sim < SIMILARITY_THRESHOLD or len(' '.join(current_chunk)) >= MAX_CHUNK_SIZE:
                chunk_text = ' '.join(current_chunk[:-1])
                if chunk_text.strip():
                    chunks.append(chunk_text)
                current_chunk = [sentence]
                current_chunk_embeddings = [current_chunk_embeddings[-1]]

    if current_chunk:
        chunk_text = ' '.join(current_chunk)
        if chunk_text.strip():
            chunks.append(chunk_text)
    return chunks

@task(log_prints=True)
def process_content(content: Content):
    """
    Processes a single content item by generating embeddings and chunking the text.
    """
    text_to_encode = ""
    if content.title:
        text_to_encode += content.title + ". "
    if content.text_content:
        text_to_encode += content.text_content

    if text_to_encode.strip():
        chunks = semantic_chunking(text_to_encode)
        chunk_objects = []
        chunk_embeddings_list = []

        for idx, chunk_text in enumerate(chunks):
            chunk_embeddings = encode_text(chunk_text)
            chunk_embeddings_list.append(chunk_embeddings)

            chunk_object = {
                "chunk_number": idx,
                "text": chunk_text,
                "embeddings": chunk_embeddings
            }
            chunk_objects.append(chunk_object)

        # Overall content embedding = mean of chunk embeddings
        if chunk_embeddings_list:
            content.embeddings = np.mean(chunk_embeddings_list, axis=0).tolist()

        content_dict = content.dict(exclude_unset=True)
        content_dict["chunks"] = chunk_objects
        content_dict["id"] = str(content.id)

        print(f"Generated embeddings for content: {content.url}, #chunks: {len(chunks)}")
        return content_dict
    else:
        print(f"No text available to generate embeddings for content: {content.url}")
        return None

@task(retries=3, retry_delay_seconds=60, log_prints=True)
def retrieve_contents_from_redis(batch_size: int) -> List[Content]:
    """
    Retrieves a batch of contents from Redis for processing.
    """
    redis_conn = Redis.from_url(get_redis_url(), db=5, decode_responses=True)
    try:
        batch = redis_conn.lrange('contents_without_embedding_queue', 0, batch_size - 1)
        redis_conn.ltrim('contents_without_embedding_queue', batch_size, -1)
        return [Content(**json.loads(content)) for content in batch]
    finally:
        redis_conn.close()

@task(log_prints=True)
def write_contents_to_redis(contents_with_embeddings: List[dict]):
    """
    Writes the processed contents with embeddings back to Redis.
    """
    redis_conn = Redis.from_url(get_redis_url(), db=6, decode_responses=True)
    try:
        serialized_contents = [json.dumps(c) for c in contents_with_embeddings if c]
        if serialized_contents:
            redis_conn.lpush('contents_with_embeddings', *serialized_contents)
            print(f"Wrote {len(serialized_contents)} contents with embeddings to Redis")
        else:
            print("No contents to write to Redis")
    finally:
        redis_conn.close()

@flow(log_prints=True, task_runner=ConcurrentTaskRunner())
def generate_embeddings_flow(batch_size: int):
    """
    The main flow to retrieve, process, and store content embeddings.
    """
    print("Starting embeddings generation process")
    raw_contents = retrieve_contents_from_redis(batch_size)

    contents_with_embeddings = []
    for raw_content in raw_contents:
        content_dict = process_content(raw_content)
        if content_dict:
            contents_with_embeddings.append(content_dict)

    write_contents_to_redis(contents_with_embeddings)
    print("Embeddings generation process completed")

# -------------------------------------------------------------------
# OPTIONAL: For local testing only (without Prefect deployment)
# -------------------------------------------------------------------
# if __name__ == "__main__":
#     # Just run flow once with some default params
#     generate_embeddings_flow(batch_size=20)
