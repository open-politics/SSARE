# Base stage
FROM python:3.11-slim AS base

WORKDIR /app

ENV UV_SYSTEM_PYTHON=1

RUN apt-get update && apt-get install -y git wget gnupg2 supervisor

RUN pip install uv

# Copy the requirements.txt file
COPY services/scraper-service/requirements.txt .
RUN uv pip install --no-cache-dir -r requirements.txt

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' && \
    apt-get update && apt-get install -y google-chrome-stable

RUN playwright install

# Copy the core directory
COPY ../../core/ ./core

# Copy the scraper service files
COPY services/scraper-service/ .

# Copy the scraping script
COPY flows/scraping/ .