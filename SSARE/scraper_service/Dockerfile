FROM python:3.9

WORKDIR /app

COPY SSARE/scraper_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY SSARE/core ./core
COPY SSARE/scraper_service/main.py .
COPY SSARE/scraper_service/scrapers ./scrapers

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
