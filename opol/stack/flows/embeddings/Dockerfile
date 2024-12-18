FROM python:3.11-slim AS base

WORKDIR /app

COPY services/embedding-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/.

RUN apt-get update && apt-get install -y curl

COPY ../../core/ ./core

COPY flows/embeddings/generate_embeddings_onebatch.py .
CMD ["python", "generate_embeddings_onebatch.py"]