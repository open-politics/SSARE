FROM python:3.11-slim AS base

WORKDIR /app

# Copy the requirements.txt file
COPY entity-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Flow service stage
FROM base AS flow
COPY entity-service/main.py .
COPY entity-service/flows/extract_entities.py .
CMD ["python", "extract_entities.py"]

# API service stage
FROM base AS api
COPY entity-service/main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "1290"]
