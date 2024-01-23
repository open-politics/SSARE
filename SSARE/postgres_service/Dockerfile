FROM python:3.9

WORKDIR /app

# Copy the requirements.txt file
COPY ./SSARE/postgres_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ./SSARE/core ./core

# Copy the main.py and other files from postgres_service
COPY ./SSARE/postgres_service/main.py .
COPY ./SSARE/postgres_service/sql_commands ./sql_commands
COPY ./SSARE/postgres_service/init.sql .
COPY ./SSARE/postgres_service/config.ini .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5432"]
