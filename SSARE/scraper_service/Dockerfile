FROM python:3.9

WORKDIR /app

# Copy the requirements.txt file
COPY scraper_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright dependencies
RUN apt-get update && apt-get install -y wget gnupg2
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list'
RUN apt-get update && apt-get install -y google-chrome-stable

# Install Playwright
RUN playwright install

RUN apt-get install -y supervisor

# Copy the core directory
COPY core ./core

# Copy the main.py and other files from scraper_service
COPY scraper_service/main.py .
COPY scraper_service/scrapers ./scrapers
COPY scraper_service/scrapers/scrapers_config.json .
COPY scraper_service/celery_worker.py .

# Copy the supervisord.conf file
COPY core/configs/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]