FROM python:3.11-slim

WORKDIR /app

# Copy the requirements.txt file
COPY reranker-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Copy the main.py and other files from postgres-service
COPY reranker-service/main.py .

COPY reranker-service/start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
