FROM python:3.11-slim AS base

WORKDIR /app

COPY embedding_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/.

RUN apt-get update && apt-get install -y curl

COPY core ./core

# Flow service stage
FROM base AS flow
COPY embedding_service/flows/generate_embeddings.py .
CMD ["python", "generate_embeddings.py"]

# API service stage
FROM base AS api
COPY embedding_service/main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "0420"]