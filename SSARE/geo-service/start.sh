#!/bin/bash
set -e

cd /app

# Run the Prefect deployment in the background
python -m flows.geocode_locations &

# Start the server in the background
echo "Starting the server on port 3690"
uvicorn main:app --host 0.0.0.0 --port 3690 &

# Wait for all background processes to finish
wait