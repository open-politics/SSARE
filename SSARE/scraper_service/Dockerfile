FROM python:3.9

WORKDIR /app

COPY /scraper_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY /core ./core
COPY /scraper_service/main.py .
COPY /scraper_service/scrapers ./scrapers
COPY /scraper_service/scrapers/scrapers_config.json .
COPY /scraper_service/celery_worker.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
