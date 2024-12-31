FROM python:3.11-slim AS base

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y curl git

RUN pip install uv

COPY services/service-embeddings/requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

COPY ../../core/ ./core

COPY flows/embeddings/ .

COPY flows/embeddings/tests/ ./

COPY flows/embeddings/start.sh .

RUN chmod +x start.sh