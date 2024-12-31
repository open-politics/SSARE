FROM python:3.11-slim AS base

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y curl git

RUN pip install uv

COPY services/service-embeddings/requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/.

RUN apt-get update && apt-get install -y curl

COPY ../../core/ ./core

COPY services/service-embeddings/main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "0420"]