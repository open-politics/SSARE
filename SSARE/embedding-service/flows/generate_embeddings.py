from typing import List, Union
import os
from prefect import flow, task
from redis import Redis
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from core.models import Content
from core.utils import get_redis_url
import nltk

from prefect.logging import get_run_logger

import asyncio

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
    global model
    if model is None:
        token = os.getenv("HUGGINGFACE_TOKEN")
        model = SentenceTransformer(
            "jinaai/jina-embeddings-v2-base-en",
            trust_remote_code=True
        )
    return model

def encode_text(texts: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
    """
    Encodes a single text string or a list of text strings into embeddings.
    """
    model = get_model()
    return model.encode(texts).tolist()

def semantic_chunking(text: str) -> List[str]:
    """
    Splits the input text into semantically coherent chunks based on sentence embeddings.
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

        # Calculate the overall content embeddings as the mean of chunk embeddings
        if chunk_embeddings_list:
            content.embeddings = np.mean(chunk_embeddings_list, axis=0).tolist()

        content_dict = content.dict(exclude_unset=True)
        content_dict["chunks"] = chunk_objects
        content_dict["id"] = str(content.id)

        print(f"Generated embeddings for content: {content.url}, Number of chunks: {len(chunks)}")
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
        serialized_contents = [json.dumps(content) for content in contents_with_embeddings if content]
        if serialized_contents:
            redis_conn.lpush('contents_with_embeddings', *serialized_contents)
            print(f"Wrote {len(serialized_contents)} contents with embeddings to Redis")
        else:
            print("No contents to write to Redis")
    finally:
        redis_conn.close()

@flow(log_prints=True)
def generate_embeddings_flow(batch_size: int):
    """
    The main flow that orchestrates the retrieval, processing, and storage of content embeddings.
    """
    print("Starting embeddings generation process")
    raw_contents = retrieve_contents_from_redis(batch_size)
    
    # Split raw_contents into 5 sets
    sets = [raw_contents[i::5] for i in range(5)]
    
    # Submit only 5 tasks, each processing a set of contents
    futures = [process_content_set(content_set) for content_set in sets]
    
    # Collect results from each task
    contents_with_embeddings = []
    for future in futures:
        contents_with_embeddings.extend(future.result())
    
    write_contents_to_redis(contents_with_embeddings)
    print("Embeddings generation process completed")

@task(log_prints=True)
def process_content_set(content_set: List[Content]) -> List[dict]:
    """
    Processes a set of content items by generating embeddings and chunking the text.
    """
    contents_with_embeddings = []
    for content in content_set:
        content_dict = process_content(content)
        if content_dict:
            contents_with_embeddings.append(content_dict)
    return contents_with_embeddings

if __name__ == "__main__":
    generate_embeddings_flow.serve(
        name="generate-embeddings-deployment",
        cron="*/5 * * * *",
        parameters={"batch_size": 20}
    )
