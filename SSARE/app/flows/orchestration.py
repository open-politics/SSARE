from prefect import task, flow, get_run_logger
import httpx
import prefect

runtime_url = "http://main_core_app:8080"

service_urls = {
    "main_core_app": runtime_url,
    "postgres_service": "http://postgres_service:5434",
    "nlp_service": "http://nlp_service:0420",
    "qdrant_service": "http://qdrant_service:6969",
    "qdrant_storage": "http://qdrant_storage:6333",
    "scraper_service": "http://scraper_service:8081",
}

@task
def produce_flags():
    response = httpx.get(f"{service_urls['postgres_service']}/flags")
    get_run_logger().info(f"produce_flags: {response.status_code}")
    return response.status_code == 200

@task
def create_scrape_jobs():
    response = httpx.post(f"{service_urls['scraper_service']}/create_scrape_jobs")
    get_run_logger().info(f"create_scrape_jobs: {response.status_code}")
    return response.status_code == 200

@task
def store_raw_articles():
    response = httpx.post(f"{service_urls['postgres_service']}/store_raw_articles")
    get_run_logger().info(f"store_raw_articles: {response.status_code}")
    return response.status_code == 200

@task
def deduplicate_articles():
    response = httpx.post(f"{service_urls['postgres_service']}/deduplicate_articles")
    get_run_logger().info(f"deduplicate_articles: {response.status_code}")
    return response.status_code == 200

@task
def create_embedding_jobs():
    response = httpx.post(f"{service_urls['postgres_service']}/create_embedding_jobs")
    get_run_logger().info(f"create_embedding_jobs: {response.status_code}")
    return response.status_code == 200

@task
def generate_embeddings():
    response = httpx.post(f"{service_urls['nlp_service']}/generate_embeddings", timeout=400)
    get_run_logger().info(f"generate_embeddings: {response.status_code}")
    return response.status_code == 200

@task
def store_articles_with_embeddings():
    response = httpx.post(f"{service_urls['postgres_service']}/store_articles_with_embeddings")
    get_run_logger().info(f"store_articles_with_embeddings: {response.status_code}")
    return response.status_code == 200

@task
def push_articles_to_qdrant_queue():
    response = httpx.post(f"{service_urls['postgres_service']}/trigger_qdrant_queue_push")
    get_run_logger().info(f"push_articles_to_qdrant_queue: {response.status_code}")
    return response.status_code == 200

@task
def store_embeddings_in_qdrant():
    response = httpx.post(f"{service_urls['qdrant_service']}/store_embeddings")
    get_run_logger().info(f"store_embeddings_in_qdrant: {response.status_code}")
    return response.status_code == 200

@flow
def scraping_flow():
    flags_result = produce_flags()
    if not flags_result:
        raise ValueError("Failed to produce flags.")
    
    scrape_result = create_scrape_jobs()
    if not scrape_result:
        raise ValueError("Failed to create scrape jobs.")
    
    store_raw_result = store_raw_articles()
    if not store_raw_result:
        raise ValueError("Failed to store raw articles.")
    
    deduplicate_result = deduplicate_articles()
    if not deduplicate_result:
        raise ValueError("Failed to deduplicate articles.")
    
    embedding_jobs_result = create_embedding_jobs()
    if not embedding_jobs_result:
        raise ValueError("Failed to create embedding jobs.")
    
    generate_embeddings_result = generate_embeddings()
    if not generate_embeddings_result:
        raise ValueError("Failed to generate embeddings.")
    
    store_embeddings_result = store_articles_with_embeddings()
    if not store_embeddings_result:
        raise ValueError("Failed to store articles with embeddings.")
    
    push_to_queue_result = push_articles_to_qdrant_queue()
    if not push_to_queue_result:
        raise ValueError("Failed to push articles to Qdrant queue.")
    
    store_result = store_embeddings_in_qdrant()
    if not store_result:
        raise ValueError("Failed to store embeddings in Qdrant.")


