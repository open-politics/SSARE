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

    # Base URL for services
    BASE_URL = os.getenv('BASE_URL', 'http://localhost')

    # Service URLs
    service_urls = {
        "main_core_app": f"{BASE_URL}:{MAIN_CORE_APP_PORT}",
        "postgres_service": f"{BASE_URL}:{POSTGRES_SERVICE_PORT}",
        "nlp_service": f"{BASE_URL}:{NLP_SERVICE_PORT}",
        "qdrant_service": f"{BASE_URL}:{QDRANT_SERVICE_PORT}",
        "qdrant_storage": f"{BASE_URL}:{QDRANT_STORAGE_PORT}",
        "scraper_service": f"{BASE_URL}:{SCRAPER_SERVICE_PORT}",
        "rag_service": f"{BASE_URL}:{RAG_SERVICE_PORT}",
        "entity_service": f"{BASE_URL}:{ENTITY_SERVICE_PORT}",
        "geo_service": f"{BASE_URL}:{GEO_SERVICE_PORT}",
        "redis": f"{BASE_URL}:{REDIS_PORT}",
        "prefect_server": f"{BASE_URL}:{PREFECT_SERVER_PORT}",
        "pelias_placeholder": f"{BASE_URL}:{PELIAS_PLACEHOLDER_PORT}",
        "r2r": f"{BASE_URL}:{R2R_PORT}",
        "neo4j_http": f"{BASE_URL}:{NEO4J_HTTP_PORT}",
        "neo4j_bolt": f"{BASE_URL}:{NEO4J_BOLT_PORT}",
    }

    # Other configurations
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    HUGGINGFACE_TOKEN = os.getenv('HUGGINGFACE_TOKEN')
    CONFIG_OPTION = os.getenv('CONFIG_OPTION', 'default')

config = ServiceConfig()