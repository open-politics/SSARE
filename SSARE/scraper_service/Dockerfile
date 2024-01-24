FROM python:3.9

WORKDIR /app

# Copy the requirements.txt file
COPY scraper_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y supervisor

# Copy the core directory
COPY core ./core

# Copy the main.py and other files from scraper_service
COPY scraper_service/main.py .
COPY scraper_service/scrapers ./scrapers
COPY scraper_service/scrapers/scrapers_config.json .
COPY scraper_service/celery_worker.py .

# Copy the supervisord.conf file
COPY service_configs/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]

