FROM python:3.11-slim AS base

WORKDIR /app

COPY services/classification-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ../../core/ ./core
COPY services/classification-service/ .

CMD ["uvicorn", "main2:app", "--host", "0.0.0.0", "--port", "5688"]
