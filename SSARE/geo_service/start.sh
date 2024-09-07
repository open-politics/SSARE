#!/bin/bash
set -e

cd /app

# Start the server
echo "Starting the server on port 3690"
uvicorn main:app --host 0.0.0.0 --port 3690 