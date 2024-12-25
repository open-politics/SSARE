FROM python:3.11-slim AS base

WORKDIR /app

COPY services/embedding-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/.

RUN apt-get update && apt-get install -y curl

COPY ../../core/ ./core

COPY flows/embeddings/tests/ ./

COPY flows/embeddings/generate_embeddings_onebatch.py .

COPY flows/embeddings/start.sh .

RUN chmod +x start.sh
CMD ["./start.sh"]