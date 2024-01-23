ALTER ROLE project_admin SUPERUSER;

CREATE TABLE IF NOT EXISTS unprocessed_articles (
    url VARCHAR(255) PRIMARY KEY,
    headline TEXT,
    paragraphs TEXT
);
