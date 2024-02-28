FROM python:3.9

WORKDIR /app

# Setup the start script
COPY postgres_service/start.sh /start.sh
RUN chmod +x /start.sh

# Copy the requirements.txt file
COPY postgres_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY core ./core

# Copy the main.py and other files from postgres_service
COPY postgres_service/main.py .

CMD ["/start.sh"]
