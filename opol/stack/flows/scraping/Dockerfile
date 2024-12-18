# Base stage
FROM python:3.11

WORKDIR /app

COPY services/scraper-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get update && apt-get install -y wget gnupg2
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
RUN apt-get update && apt-get install -y google-chrome-stable

RUN playwright install
RUN apt-get install -y supervisor

COPY ../../core/ ./core
COPY services/scraper-service/ .

COPY flows/scraping/scraping_flow.py .
COPY flows/scraping/tasks/ ./tasks

CMD ["python", "scraping_flow.py"]