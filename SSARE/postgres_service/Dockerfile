FROM python:3.9

WORKDIR /app

COPY /postgres_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY /core ./core
COPY /postgres_service/main.py .
COPY /postgres_service/sql_commands ./sql_commands
COPY /postgres_service/init.sql .
COPY /postgres_service/config.ini . 

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5432"]
