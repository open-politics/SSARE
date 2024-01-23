FROM python:3.9

WORKDIR /app

# Copy the requirements.txt file
COPY ./SSARE/scraper_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ./SSARE/core ./core

# Copy the main.py and other files from scraper_service
COPY ./SSARE/scraper_service/main.py .
COPY ./SSARE/scraper_service/scrapers ./scrapers
COPY ./SSARE/scraper_service/scrapers/scrapers_config.json .
COPY ./SSARE/scraper_service/celery_worker.py .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8081"]
