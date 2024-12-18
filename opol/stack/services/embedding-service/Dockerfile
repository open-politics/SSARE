FROM python:3.11-slim AS base

WORKDIR /app

COPY services/embedding-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/.

RUN apt-get update && apt-get install -y curl

COPY ../../core/ ./core

COPY services/embedding-service/main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "0420"]