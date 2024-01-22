ALTER ROLE project_admin SUPERUSER;

CREATE TABLE IF NOT EXISTS open_politics_intermediate_articles (
    url VARCHAR(255) PRIMARY KEY,
    headline TEXT,
    paragraphs TEXT
);
