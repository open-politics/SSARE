#!/bin/bash

# Deploy flows using Prefect CLI
python -m flows.orchestration &

# Start the Uvicorn server
uvicorn main:app --host 0.0.0.0 --port 8089