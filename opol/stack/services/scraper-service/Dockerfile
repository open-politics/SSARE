# Base stage
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends wget gnupg2 && \
    wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' && \
    apt-get update && \
    apt-get install -y --no-install-recommends google-chrome-stable supervisor && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/scraper-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ../../core/ ./core
COPY services/scraper-service/ .

# Set the entrypoint
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
