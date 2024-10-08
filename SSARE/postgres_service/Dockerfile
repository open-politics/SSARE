FROM python:3.11-slim

WORKDIR /app

# Set PYTHONPATH
ENV PYTHONPATH=/app/postgres_service:$PYTHONPATH

# Copy the requirements.txt file
COPY postgres_service/requirements.txt .
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Copy the postgres_service directory
COPY postgres_service ./postgres_service

RUN chmod +x postgres_service/start.sh

CMD ["./postgres_service/start.sh"]