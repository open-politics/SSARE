FROM python:3.11

WORKDIR /app

# Install cron
RUN apt-get update && apt-get -y install cron

# Copy requirements file
COPY services/app/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY services/app/ .
COPY ../../core/ core
COPY flows/orchestration/ ./flows

# Copy the start script and make it executable
COPY services/app/start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]