FROM python:3.11-slim

WORKDIR /app

# Copy the requirements.txt file
COPY embedding_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Copy the main.py and other files from postgres_service
COPY embedding_service/main.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "0420"]
