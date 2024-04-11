#!/bin/bash

# Start the services using Docker Compose
docker-compose up -d

# Wait for the Prefect server to be ready
until docker-compose exec prefect_server prefect server health-check &> /dev/null
do
    echo "Waiting for Prefect server to be ready..."
    sleep 5
done

# Register the flow with the Prefect server
docker-compose exec prefect_cli prefect deployment build /root/flows/orchestration.py:scraping_flow -n "Scraping Flow" --apply

# Start the flow run
docker-compose exec prefect_cli prefect deployment run "Scraping Flow"

echo "Services and pipelines launched successfully!"
