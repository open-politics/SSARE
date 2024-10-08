FROM python:3.11-slim

WORKDIR /app

# Copy the requirements.txt file
COPY reranker_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Copy the main.py and other files from postgres_service
COPY reranker_service/main.py .

COPY reranker_service/start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
