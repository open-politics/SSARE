import os

class ServiceConfig:
    # Service Ports
    MAIN_CORE_APP_PORT = os.getenv('MAIN_CORE_APP_PORT', '8089')
    POSTGRES_SERVICE_PORT = os.getenv('POSTGRES_SERVICE_PORT', '5434')
    NLP_SERVICE_PORT = os.getenv('NLP_SERVICE_PORT', '0420')
    QDRANT_SERVICE_PORT = os.getenv('QDRANT_SERVICE_PORT', '6969')
    QDRANT_STORAGE_PORT = os.getenv('QDRANT_STORAGE_PORT', '6333')
    SCRAPER_SERVICE_PORT = os.getenv('SCRAPER_SERVICE_PORT', '8081')
    RAG_SERVICE_PORT = os.getenv('RAG_SERVICE_PORT', '4312')
    ENTITY_SERVICE_PORT = os.getenv('ENTITY_SERVICE_PORT', '1290')
    GEO_SERVICE_PORT = os.getenv('GEO_SERVICE_PORT', '3690')
    REDIS_PORT = os.getenv('REDIS_PORT', '6379')
    PREFECT_SERVER_PORT = os.getenv('PREFECT_SERVER_PORT', '4200')
    PELIAS_PLACEHOLDER_PORT = os.getenv('PELIAS_PLACEHOLDER_PORT', '3999')
    R2R_PORT = os.getenv('R2R_PORT', '8000')
    RAG_SERVICE_PORT = os.getenv('RAG_SERVICE_PORT', '4312')
    NEO4J_HTTP_PORT = os.getenv('NEO4J_HTTP_PORT', '7474')
    NEO4J_BOLT_PORT = os.getenv('NEO4J_BOLT_PORT', '7687')

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
    ARTICLES_DB_PORT = os.getenv('ARTICLES_DB_PORT', '5434')

    # Service URLs
    service_urls = {
        "main_core_app": f"http://main_core_app:{MAIN_CORE_APP_PORT}",
        "postgres_service": f"http://postgres_service:{POSTGRES_SERVICE_PORT}",
        "nlp_service": f"http://nlp_service:{NLP_SERVICE_PORT}",
        "qdrant_service": f"http://qdrant_service:{QDRANT_SERVICE_PORT}",
        "qdrant_storage": f"http://qdrant_storage:{QDRANT_STORAGE_PORT}",
        "scraper_service": f"http://scraper_service:{SCRAPER_SERVICE_PORT}",
        "rag_service": f"http://rag_service:{RAG_SERVICE_PORT}",
        "entity_service": f"http://entity_service:{ENTITY_SERVICE_PORT}",
        "geo_service": f"http://geo_service:{GEO_SERVICE_PORT}",
        "redis": f"redis://redis:{REDIS_PORT}",
        "prefect_server": f"http://prefect_server:{PREFECT_SERVER_PORT}",
        "pelias_placeholder": f"http://pelias_placeholder:{PELIAS_PLACEHOLDER_PORT}",
        "r2r": f"http://r2r:{R2R_PORT}",
        "rag_service": f"http://rag_service:{RAG_SERVICE_PORT}",
        "neo4j_http": f"http://neo4j:{NEO4J_HTTP_PORT}",
        "neo4j_bolt": f"bolt://neo4j:{NEO4J_BOLT_PORT}",
    }

    # Redis channel mappings
    redis_queues = {
        "articles_without_embedding_queue": {"db": 5, "key": "articles_without_embedding_queue"},
        "articles_with_entities_queue": {"db": 2, "key": "articles_with_entities_queue"},
        "scrape_sources": {"db": 0, "key": "scrape_sources"},
        "raw_articles_queue": {"db": 1, "key": "raw_articles_queue"},
        "articles_with_embeddings": {"db": 6, "key": "articles_with_embeddings"},
        "articles_without_entities_queue": {"db": 2, "key": "articles_without_entities_queue"},
        "articles_without_geocoding_queue": {"db": 3, "key": "articles_without_geocoding_queue"},
        "scraping_in_progress": {"db": 0, "key": "scraping_in_progress"}
    }

    # Other configurations/ API Keys
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    HUGGINGFACE_TOKEN = os.getenv('HUGGINGFACE_TOKEN')
    CONFIG_OPTION = os.getenv('CONFIG_OPTION', 'default')

config = ServiceConfig()