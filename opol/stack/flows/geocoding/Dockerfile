FROM python:3.11-slim

WORKDIR /app

# Copy the requirements.txt file
COPY services/geo-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the core directory
COPY ../../core/ ./core

COPY flows/geocoding/geocode_locations.py .

CMD ["python", "geocode_locations.py"]
