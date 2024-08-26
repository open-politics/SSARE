#!/bin/bash

# Set up cron jobs
echo "*/30 * * * * python /app/flows/orchestration.py scraping_flow" >> /etc/crontab
echo "*/6 * * * * python /app/flows/orchestration.py embedding_flow" >> /etc/crontab
echo "*/6 * * * * python /app/flows/orchestration.py entity_extraction_flow" >> /etc/crontab
echo "*/6 * * * * python /app/flows/orchestration.py geocoding_flow" >> /etc/crontab
echo "*/6 * * * * python /app/flows/orchestration.py classification_flow" >> /etc/crontab

# Start cron
cron

# The Uvicorn server will be started by the CMD instruction in the Dockerfile

# Keep the container running
tail -f /dev/null