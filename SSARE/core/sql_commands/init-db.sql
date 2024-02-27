CREATE USER qdrant WITH PASSWORD 'qdrant';
GRANT ALL PRIVILEGES ON DATABASE news TO qdrant;

CREATE TABLE articles (
    url TEXT PRIMARY KEY,
    headline TEXT,
    paragraphs TEXT,
    source TEXT,
    embeddings TEXT,  -- Adjust the datatype as needed.
    embeddings_created BOOLEAN DEFAULT FALSE,
    isStored_in_qdrant BOOLEAN DEFAULT FALSE
);


postgres_db = open_politics