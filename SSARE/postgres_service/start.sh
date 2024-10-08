#!/bin/bash
set -e

cd /app

# Run migrations
echo "Running database migrations..."
bash postgres_service/prestart.sh

# Start the server
echo "Starting the server on port 5434"
uvicorn postgres_service.main:app --host 0.0.0.0 --port 5434