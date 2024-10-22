import json
import logging
import time
import numpy as np
import nltk
from redis import Redis
from fastapi import FastAPI, HTTPException
from sentence_transformers import SentenceTransformer
from sqlmodel import Session
from typing import List, Optional
from prefect import task, flow
from core.models import Content, ContentChunk
from core.service_mapping import ServiceConfig
from core.utils import logger
from prefect_ray.task_runners import RayTaskRunner

app = FastAPI()

# Download 'punkt' tokenizer if not already downloaded
nltk.download('punkt')

# Model Initialization
config = ServiceConfig()
token = config.HUGGINGFACE_TOKEN
model = SentenceTransformer(
    "jinaai/jina-embeddings-v2-base-en",
    use_auth_token=token,
    trust_remote_code=True
)

@app.get("/healthz")
async def healthcheck():
    return {"message": "NLP Service Running"}, 200

@task
def retrieve_contents_from_redis(redis_conn_raw, batch_size=50):
    batch = redis_conn_raw.lrange('contents_without_embedding_queue', 0, batch_size - 1)
    redis_conn_raw.ltrim('contents_without_embedding_queue', batch_size, -1)
    return [Content(**json.loads(content)) for content in batch]

def semantic_chunking(text, max_chunk_size=512, similarity_threshold=0.95):
    # Tokenize text into sentences
    sentences = nltk.sent_tokenize(text, language='english')

    # Encode each sentence using your model
    sentence_embeddings = model.encode(sentences)

    chunks = []
    current_chunk = []
    current_chunk_embeddings = []

    for i, sentence in enumerate(sentences):
        current_chunk.append(sentence)
        current_chunk_embeddings.append(sentence_embeddings[i])

        # Check if we should start a new chunk
        if len(current_chunk_embeddings) > 1:
            # Compute cosine similarity between the last two sentence embeddings
            vec_a = current_chunk_embeddings[-1]
            vec_b = current_chunk_embeddings[-2]

            # Calculate cosine similarity using NumPy
            cos_sim = np.dot(vec_a, vec_b) / (np.linalg.norm(vec_a) * np.linalg.norm(vec_b))

            # Start a new chunk if similarity is below threshold or max chunk size exceeded
            if cos_sim < similarity_threshold or len(' '.join(current_chunk)) >= max_chunk_size:
                chunk_text = ' '.join(current_chunk[:-1])
                if chunk_text.strip():
                    chunks.append(chunk_text)
                # Reset current chunk
                current_chunk = [sentence]
                current_chunk_embeddings = [current_chunk_embeddings[-1]]

    # Add the last chunk
    if current_chunk:
        chunk_text = ' '.join(current_chunk)
        if chunk_text.strip():
            chunks.append(chunk_text)
    logger.warning(f"Chunks: {chunks}")
    return chunks

@task
def process_content(content: Content):
    # Combine title and text content
    text_to_encode = ""
    if content.title:
        text_to_encode += content.title + ". "
    if content.text_content:
        text_to_encode += content.text_content

    # Only generate embeddings if there's text to encode
    if text_to_encode.strip():
        # Perform semantic chunking
        chunks = semantic_chunking(text_to_encode)
        chunk_objects = []
        chunk_embeddings_list = []

        for idx, chunk_text in enumerate(chunks):
            # Generate embeddings for each chunk
            chunk_embeddings = model.encode(chunk_text).tolist()
            chunk_embeddings_list.append(chunk_embeddings)

            # Create dictionary representing ContentChunk
            chunk_object = {
                "chunk_number": idx,
                "text": chunk_text,
                "embeddings": chunk_embeddings
            }
            chunk_objects.append(chunk_object)

        # Update the content with new embeddings (average of chunk embeddings)
        content.embeddings = np.mean(chunk_embeddings_list, axis=0).tolist()

        # Add chunks to content
        content_dict = content.dict(exclude_unset=True)
        content_dict["chunks"] = chunk_objects
        content_dict["id"] = str(content.id)  # Ensure id is included

        logger.info(f"Generated embeddings for content: {content.url}, Number of chunks: {len(chunks)}")
        return content_dict
    else:
        logger.warning(f"No text available to generate embeddings for content: {content.url}")
        return None

@task
def write_contents_to_redis(redis_conn_processed, contents_with_embeddings):
    serialized_contents = []
    for content in contents_with_embeddings:
        if content:
            serialized_contents.append(json.dumps(content))
    if serialized_contents:  # Check if the list is not empty
        redis_conn_processed.lpush('contents_with_embeddings', *serialized_contents)
        logger.info(f"Wrote {len(serialized_contents)} contents with embeddings to Redis")
    else:
        logger.info("No contents to write to Redis")

@flow(task_runner=RayTaskRunner())
def generate_embeddings_flow(batch_size: int):
    logger.info("Starting embeddings generation process")
    redis_conn_raw = Redis(host='redis', port=6379, db=5, decode_responses=True)
    redis_conn_processed = Redis(host='redis', port=6379, db=6, decode_responses=True)

    try:
        raw_contents = retrieve_contents_from_redis(redis_conn_raw, batch_size)
        contents_with_embeddings = [process_content(content) for content in raw_contents]
        write_contents_to_redis(redis_conn_processed, contents_with_embeddings)
    finally:
        redis_conn_raw.close()
        redis_conn_processed.close()
        time.sleep(1)

    logger.info("Embeddings generation process completed")

@app.post("/generate_embeddings")
def generate_embeddings(batch_size: int = 100):
    logger.debug("GENERATING EMBEDDINGS")
    generate_embeddings_flow(batch_size)
    return {"message": "Embeddings generated successfully"}

@app.get("/generate_query_embeddings")
def generate_query_embedding(query: str):
    try:
        embeddings = model.encode(query).tolist()
        logger.info(f"Generated embeddings for query: {query}, Embeddings Length: {len(embeddings)}")
        return {"embeddings": embeddings}
    except Exception as e:
        logger.error(f"Error generating embeddings: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
