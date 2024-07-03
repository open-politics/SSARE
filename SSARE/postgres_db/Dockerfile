# Use the official PostgreSQL image as a base
FROM postgres:latest

# Install dependencies
RUN apt-get update && apt-get install -y \
    postgresql-server-dev-all \
    build-essential \
    git

# Clone pgvector repository and install the extension
RUN cd /tmp && \
    git clone --branch v0.7.2 https://github.com/pgvector/pgvector.git && \
    cd pgvector && \
    make && \
    make install

# Copy the initialization script to the Docker entrypoint init directory
COPY postgres_db/initdb.sh /docker-entrypoint-initdb.d/

