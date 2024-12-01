import os

class ServiceConfig:
    ## Service Ports

    MAIN_CORE_APP_PORT = os.getenv('MAIN_CORE_APP_PORT', '8089')
    POSTGRES_SERVICE_PORT = os.getenv('POSTGRES_SERVICE_PORT', '5434')
    EMBEDDING_SERVICE_PORT = os.getenv('EMBEDDING_SERVICE_PORT', '0420')
    QDRANT_SERVICE_PORT = os.getenv('QDRANT_SERVICE_PORT', '6969')
    QDRANT_STORAGE_PORT = os.getenv('QDRANT_STORAGE_PORT', '6333')
    SCRAPER_SERVICE_PORT = os.getenv('SCRAPER_SERVICE_PORT', '8081')
    RAG_SERVICE_PORT = os.getenv('RAG_SERVICE_PORT', '4312')
    ENTITY_SERVICE_PORT = os.getenv('ENTITY_SERVICE_PORT', '1290')
    GEO_SERVICE_PORT = os.getenv('GEO_SERVICE_PORT', '3690')
    RERANKER_SERVICE_PORT = os.getenv('RERANKER_SERVICE_PORT', '6930')
    REDIS_PORT = os.getenv('REDIS_PORT', '6379')
    PREFECT_SERVER_PORT = os.getenv('PREFECT_SERVER_PORT', '4200')
    PELIAS_PLACEHOLDER_PORT = os.getenv('PELIAS_PLACEHOLDER_PORT', '3999')
    R2R_PORT = os.getenv('R2R_PORT', '8000')
    NEO4J_HTTP_PORT = os.getenv('NEO4J_HTTP_PORT', '7474')
    NEO4J_BOLT_PORT = os.getenv('NEO4J_BOLT_PORT', '7687')
    LITELLM_PORT = os.getenv('LITELLM_PORT', '11435')
    CLASSIFICATION_SERVICE_PORT = os.getenv('CLASSIFICATION_SERVICE_PORT', '5688')
    SEMANTIC_ROUTER_PORT = os.getenv('SEMANTIC_ROUTER_PORT', '5689')

    ## OLLAMA
    OLLAMA_PORT = os.getenv('OLLAMA_PORT', '11434')

    # Database configurations
    R2R_DB_USER = os.getenv('R2R_DB_USER', 'r2r_user')
    R2R_DB_PASSWORD = os.getenv('R2R_DB_PASSWORD', 'r2r_password')
    R2R_DB_NAME = os.getenv('R2R_DB_NAME', 'r2r_db')
    R2R_DB_PORT = os.getenv('R2R_DB_PORT', '5432')

    PREFECT_DB_USER = os.getenv('PREFECT_DB_USER', 'prefect_user')
    PREFECT_DB_PASSWORD = os.getenv('PREFECT_DB_PASSWORD', 'prefect_password')
    PREFECT_DB_NAME = os.getenv('PREFECT_DB_NAME', 'prefect_db')
    PREFECT_DB_PORT = os.getenv('PREFECT_DB_PORT', '5433')

    ARTICLES_DB_USER = os.getenv('ARTICLES_DB_USER', 'articles_user')
    ARTICLES_DB_PASSWORD = os.getenv('ARTICLES_DB_PASSWORD', 'articles_password')
    ARTICLES_DB_NAME = os.getenv('ARTICLES_DB_NAME', 'articles_db')
    ARTICLES_DB_PORT = os.getenv('ARTICLES_DB_PORT', '5473') ## THIS IS THE MAIN DATABASE


    # DB Mode
    DB_MODE = os.getenv('DB_MODE', 'managed')

    # Redis Mode
    REDIS_MODE = os.getenv('REDIS_MODE', 'managed')


    # Managed Database Configurations
    MANAGED_ARTICLES_DB_HOST = os.getenv('MANAGED_ARTICLES_DB_HOST', 'x')
    MANAGED_ARTICLES_DB_PORT = os.getenv('MANAGED_ARTICLES_DB_PORT', '5473')
    MANAGED_ARTICLES_DB_USER = os.getenv('MANAGED_ARTICLES_DB_USER', 'x')
    MANAGED_ARTICLES_DB_PASSWORD = os.getenv('MANAGED_ARTICLES_DB_PASSWORD', 'x')

    # Managed Redis Configuration
    MANAGED_REDIS_HOST = os.getenv('MANAGED_REDIS_HOST', 'x')
    MANAGED_REDIS_PORT = os.getenv('MANAGED_REDIS_PORT', '6379')
    
    # Determine if running in Kubernetes or Docker Compose
    RUNNING_ENV = os.getenv('RUNNING_ENV', 'compose')

    # Service URLs
    if RUNNING_ENV == 'kubernetes':
        service_urls = {
            "main_core-app": "http://main-core-app",
            "postgres-service": "http://postgres-service",
            "embedding-service": "http://embedding-service",
            "qdrant-service": "http://qdrant-service",
            "qdrant-storage": "http://qdrant-storage",
            "scraper-service": "http://scraper-service",
            "rag-service": "http://rag-service",
            "entity-service": "http://entity-service",
            "geo-service": "http://geo-service",
            "redis": "redis://redis",
            "prefect-server": "http://prefect-server",
            "reranker-service": "http://reranker-service",
            "pelias-placeholder": "http://pelias-placeholder",
            "r2r": "http://r2r",
            "neo4j-http": "http://neo4j",
            "neo4j-bolt": "bolt://neo4j",
            "ollama": "http://ollama",
            "liteLLM": "http://liteLLM",
            "classification-service": "http://classification-service",
            "semantic-router": "http://semantic-router",
        }
    else:  # Default to Docker Compose configuration
        service_urls = {
            "main_core-app": f"http://main-core-app:{MAIN_CORE_APP_PORT}",
            "postgres-service": f"http://postgres-service:{POSTGRES_SERVICE_PORT}",
            "embedding-service": f"http://embedding-service:{EMBEDDING_SERVICE_PORT}",
            "qdrant-service": f"http://qdrant-service:{QDRANT_SERVICE_PORT}",
            "qdrant-storage": f"http://qdrant-storage:{QDRANT_STORAGE_PORT}",
            "scraper-service": f"http://scraper-service:{SCRAPER_SERVICE_PORT}",
            "rag-service": f"http://rag-service:{RAG_SERVICE_PORT}",
            "entity-service": f"http://entity-service:{ENTITY_SERVICE_PORT}",
            "geo-service": f"http://geo-service:{GEO_SERVICE_PORT}",
            "redis": f"redis://redis:{REDIS_PORT}",
            "prefect-server": f"http://prefect-server:{PREFECT_SERVER_PORT}",
            "reranker-service": f"http://reranker-service:{RERANKER_SERVICE_PORT}",
            "pelias-placeholder": f"http://pelias-placeholder:{PELIAS_PLACEHOLDER_PORT}",
            "r2r": f"http://r2r:{R2R_PORT}",
            "neo4j-http": f"http://neo4j:{NEO4J_HTTP_PORT}",
            "neo4j-bolt": f"bolt://neo4j:{NEO4J_BOLT_PORT}",
            "ollama": f"http://ollama:{OLLAMA_PORT}",
            "liteLLM": f"http://liteLLM:{LITELLM_PORT}",
            "classification-service": f"http://classification-service:{CLASSIFICATION_SERVICE_PORT}",
            "semantic-router": f"http://semantic-router:{SEMANTIC_ROUTER_PORT}",
        }

    # Redis channel mappings with explicit types
    redis_queues = {
        "contents_without_embedding_queue": {"db": 5, "key": "contents_without_embedding_queue", "type": "list"},
        "contents_with_entities_queue": {"db": 2, "key": "contents_with_entities_queue", "type": "list"},
        "scrape_sources": {"db": 0, "key": "scrape_sources", "type": "list"},
        "raw_contents_queue": {"db": 1, "key": "raw_contents_queue", "type": "list"},
        "contents_with_embeddings": {"db": 6, "key": "contents_with_embeddings", "type": "list"},
        "contents_without_entities_queue": {"db": 2, "key": "contents_without_entities_queue", "type": "list"},
        "contents_without_geocoding_queue": {"db": 3, "key": "contents_without_geocoding_queue", "type": "list"},
        "contents_with_geocoding_queue": {"db": 4, "key": "contents_with_geocoding_queue", "type": "list"},
        "contents_without_classification_queue": {"db": 4, "key": "contents_without_classification_queue", "type": "list"},
        "contents_with_classification_queue": {"db": 4, "key": "contents_with_classification_queue", "type": "list"},
        "Orchestration_in_progress": {"db": 1, "key": "Orchestration_in_progress", "type": "string"},
        "scrapers_running": {"db": 1, "key": "scrapers_running", "type": "string"},
        "outward_irrelevant_queue": {"db": 7, "key": "outward_irrelevant_queue", "type": "list"}
    }


    # Other configurations/ API Keys
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    HUGGINGFACE_TOKEN = os.getenv('HUGGINGFACE_TOKEN')
    CONFIG_OPTION = os.getenv('CONFIG_OPTION', 'default')



config = ServiceConfig()


def get_db_url():
    """Get database URL based on mode"""
    if os.getenv('DB_MODE') == "managed":
        return (
            f"postgresql+asyncpg://{config.MANAGED_ARTICLES_DB_USER}:{config.MANAGED_ARTICLES_DB_PASSWORD}"
                f"@{config.MANAGED_ARTICLES_DB_HOST}:{config.MANAGED_ARTICLES_DB_PORT}/{config.ARTICLES_DB_NAME}"
            )
    else:
        return (
            f"postgresql+asyncpg://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
                f"@articles_database:{config.ARTICLES_DB_PORT}/{config.ARTICLES_DB_NAME}"
            )

def get_redis_url():
    """Get Redis URL based on mode"""
    if os.getenv('REDIS_MODE') == "managed":
        return f"redis://{config.MANAGED_REDIS_HOST}:{config.MANAGED_REDIS_PORT}"
    else:
        return f"redis://redis:{config.REDIS_PORT}"

def get_sync_db_url():
    """Get synchronous database URL for Alembic"""
    if os.getenv('DB_MODE') == "managed":
        return (
            f"postgresql://{config.MANAGED_ARTICLES_DB_USER}:{config.MANAGED_ARTICLES_DB_PASSWORD}"
                f"@{config.MANAGED_ARTICLES_DB_HOST}:{config.MANAGED_ARTICLES_DB_PORT}/{config.ARTICLES_DB_NAME}"
            )
    else:
            return (
                f"postgresql://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
                f"@articles_database:{config.ARTICLES_DB_PORT}/{config.ARTICLES_DB_NAME}"
            )
