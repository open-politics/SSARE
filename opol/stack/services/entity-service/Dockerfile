FROM python:3.11-slim

WORKDIR /app

# Copy the requirements.txt file
COPY services/entity-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ../../core/ ./core

COPY services/entity-service/main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "1290"]
