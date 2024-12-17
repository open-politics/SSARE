FROM python:3.11-slim AS base

WORKDIR /app/

# Set PYTHONPATH
ENV PYTHONPATH=/.

# Install dependencies
RUN apt-get update && \
    apt-get install -y netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

# Copy the requirements.txt file and install Python dependencies
COPY postgres-service/requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the postgres-service directory
COPY postgres-service .

# Copy the core directory
COPY ../core/ ./core
COPY postgres-service/flows ./

# Copy the alembic directory
COPY postgres-service/alembic ./alembic

# Make the start script executable
RUN chmod +x /app/start.sh

FROM base AS flow
CMD ["python", "resolve_location_entities.py"]

FROM base AS app
CMD ["/app/start.sh"]