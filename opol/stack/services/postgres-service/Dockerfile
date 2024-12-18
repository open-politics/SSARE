FROM python:3.11-slim AS base

WORKDIR /app/

# Set PYTHONPATH
ENV PYTHONPATH=/.

# Install dependencies
RUN apt-get update && \
    apt-get install -y netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements.txt file and install Python dependencies
COPY services/postgres-service/requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the postgres-service directory
COPY services/postgres-service .

# Copy the core directory
COPY ../../core/ ./core

# Copy the alembic directory
COPY services/postgres-service/alembic ./alembic
COPY services/postgres-service/start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]