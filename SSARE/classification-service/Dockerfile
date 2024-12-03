FROM python:3.11-slim AS base

WORKDIR /app

COPY classification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core ./core
COPY classification-service/ .
COPY classification-service/flows ./


# Flow service stage
FROM base AS flow
CMD ["python", "classification_flow.py"]

# API service stage
FROM base AS api
CMD ["uvicorn", "main2:app", "--host", "0.0.0.0", "--port", "5688"]
