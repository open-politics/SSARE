# Base stage
FROM python:3.11 AS base

WORKDIR /app

COPY scraper_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y wget gnupg2
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
RUN apt-get update && apt-get install -y google-chrome-stable

RUN playwright install
RUN apt-get install -y supervisor

COPY core ./core
COPY scraper_service/ .

# Flow service stage
FROM base AS flow
COPY scraper_service/flows/scraping_flow.py .
CMD ["python", "scraping_flow.py"]

# API service stage
FROM base AS api
COPY scraper_service/main.py .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]