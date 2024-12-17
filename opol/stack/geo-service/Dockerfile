FROM python:3.11-slim

WORKDIR /app

# Copy the requirements.txt file
COPY geo-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ../core/ ./core

# Copy the main.py and other files from postgres-service
COPY geo-service/main.py .
COPY geo-service/run_with_logfire.py .
COPY geo-service/flows ./flows

COPY geo-service/start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
