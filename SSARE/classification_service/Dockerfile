FROM python:3.11-slim

WORKDIR /app

COPY classification_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core ./core

COPY classification_service/main.py .
COPY classification_service/testtt.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5688"]