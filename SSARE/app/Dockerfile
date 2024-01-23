FROM python:3.9

WORKDIR /app

COPY SSARE/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY SSARE/core ./core
COPY SSARE/app/main.py .
COPY SSARE/app/config.ini .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
