FROM python:3.9

WORKDIR /app

# Copy the requirements.txt file
COPY ./SSARE/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ./SSARE/core ./core

# Copy the main.py file
COPY ./SSARE/app/main.py .

# Copy the config.ini file
COPY ./SSARE/app/config.ini .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
