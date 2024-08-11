FROM python:3.11-slim

WORKDIR /app

COPY embedding_service/requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5689"]