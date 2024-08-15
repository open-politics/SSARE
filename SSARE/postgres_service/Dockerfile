FROM python:3.11-slim

WORKDIR /app

# Set PYTHONPATH
ENV PYTHONPATH=/app:$PYTHONPATH

# Copy the requirements.txt file
COPY postgres_service/requirements.txt .
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Copy the main.py and other files from postgres_service
COPY postgres_service/main.py .

COPY postgres_service/start.sh .
COPY postgres_service/alembic.ini .
COPY postgres_service/alembic ./alembic

RUN chmod +x start.sh

CMD ["./start.sh"]