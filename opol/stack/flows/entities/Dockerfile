FROM python:3.11-slim AS base

WORKDIR /app

# Copy the requirements.txt file
COPY services/entity-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ../../core/ ./core

COPY flows/entities/extract_entities.py .
CMD ["python", "extract_entities.py"]

