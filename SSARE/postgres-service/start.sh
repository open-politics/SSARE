#!/bin/bash
set -e

cd /app

# Run migrations
echo "Running database migrations..."
bash prestart.sh

# Start the server
echo "Starting the server on port 5434"
python -m run_with_logfire