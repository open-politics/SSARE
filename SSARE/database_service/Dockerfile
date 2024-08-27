FROM python:3.11-slim

WORKDIR /app

# Set PYTHONPATH
ENV PYTHONPATH=/app:$PYTHONPATH

# Copy the requirements.txt file
COPY database_service/requirements.txt .
RUN apt-get update && apt-get install -y netcat-traditional && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Copy the main.py and other files from database_service
COPY database_service/main.py .
COPY database_service/algoquan.py .
COPY database_service/schemas.csv .

COPY database_service/start.sh .
COPY database_service/alembic.ini .
COPY database_service/alembic ./alembic

RUN chmod +x start.sh

CMD ["./start.sh"]