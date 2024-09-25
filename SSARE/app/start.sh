#!/bin/bash

# Set up cron jobs
echo "*/30 * * * * python /app/flows/orchestration.py scraping_flow >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/6 * * * * python /app/flows/orchestration.py embedding_flow >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/6 * * * * python /app/flows/orchestration.py entity_extraction_flow >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/6 * * * * python /app/flows/orchestration.py geocoding_flow >> /var/log/cron.log 2>&1" >> /etc/crontab
echo "*/6 * * * * python /app/flows/orchestration.py classification_flow >> /var/log/cron.log 2>&1" >> /etc/crontab

# Start cron
service cron start

# Start the Uvicorn server
uvicorn main:app --host 0.0.0.0 --port 8089

# Keep the container running
tail -f /var/log/cron.log