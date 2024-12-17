#!/bin/bash
set -e

cd /app

# Run the Prefect deployment in the background
# python -m flows.geocode_locations &

# Start the server in the background
echo "Starting the server on port 3690"
python -m run_with_logfire &

# Wait for all background processes to finish
wait -n

# Check if any of the background processes have exited
while true; do
  if ! pgrep -f "python -m flows.geocode_locations" > /dev/null; then
    echo "Prefect deployment has stopped. Exiting."
    exit 1
  fi

  if ! pgrep -f "python -m run" > /dev/null; then
    echo "FastAPI server has stopped. Exiting."
    exit 1
  fi

  sleep 5
done