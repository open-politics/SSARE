FROM python:3.9

WORKDIR /app

COPY /app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY /core ./core
COPY /app/main.py .
COPY /app/config.ini .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
