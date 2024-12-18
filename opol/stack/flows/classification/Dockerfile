FROM python:3.11-slim AS base

WORKDIR /app

COPY services/classification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ../../core/ ./core
COPY services/classification-service/ .
COPY flows/classification/classification_flow.py .

CMD ["python", "classification_flow.py"]

