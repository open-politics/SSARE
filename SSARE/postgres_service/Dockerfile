FROM python:3.9

WORKDIR /app

COPY SSARE/postgres_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY SSARE/core ./core
COPY SSARE/postgres_service/main.py .
COPY SSARE/postgres_service/sql_commands .
COPY SSARE/postgres_service/init.sql .
COPY SSARE/postgres_service/config.ini . 

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
