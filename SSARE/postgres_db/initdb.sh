#!/bin/bash
set -e

echo "Initializing pgvector extension and creating articles table..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;

    CREATE TABLE IF NOT EXISTS articles (
        url VARCHAR PRIMARY KEY,
        headline VARCHAR,
        paragraphs TEXT,
        source VARCHAR,
        embeddings VECTOR(768),
        entities JSONB,
        geocodes JSONB[],
        embeddings_created INTEGER DEFAULT 0,
        stored_in_qdrant INTEGER DEFAULT 0,
        entities_extracted INTEGER DEFAULT 0,
        geocoding_created INTEGER DEFAULT 0
    );
EOSQL
