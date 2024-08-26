FROM python:3.11-slim

WORKDIR /app

# Install cron
RUN apt-get update && apt-get -y install cron

# Copy requirements file
COPY app/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/ .
COPY core/ ./core
COPY flows/ ./flows

# Copy the start script and make it executable
COPY app/start.sh .
RUN chmod +x start.sh

# Use a shell to run both the start script and uvicorn
CMD ./start.sh & uvicorn main:app --host 0.0.0.0 --port 8089