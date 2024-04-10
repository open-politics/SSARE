#!/bin/bash

# Set the path to your Docker Compose file
COMPOSE_FILE="./docker-compose.yml"

# Set the path to your Prefect flows directory
FLOWS_DIR="./flows"

# Set the path to your orchestration.py file
ORCHESTRATION_FILE="./SSARE/app/orchestration.py"

# Create the flows directory if it doesn't exist
mkdir -p "$FLOWS_DIR"

# Copy the orchestration.py file to the flows directory
cp "$ORCHESTRATION_FILE" "$FLOWS_DIR"

# Build and start the services
docker-compose -f "$COMPOSE_FILE" up -d --build

# Wait for the Prefect Server to be ready
echo "Waiting for Prefect Server to be ready..."
until docker-compose -f "$COMPOSE_FILE" exec prefect_server prefect server info >/dev/null 2>&1; do
    sleep 1
done
echo "Prefect Server is ready!"

# Create a deployment for the scraping_flow
docker-compose -f "$COMPOSE_FILE" run --rm prefect_cli prefect deployment build /root/flows/orchestration.py:scraping_flow -n "Scraping Flow Deployment" -q default

# Apply the deployment
docker-compose -f "$COMPOSE_FILE" run --rm prefect_cli prefect deployment apply "Scraping Flow Deployment"

# Trigger the scraping_flow
docker-compose -f "$COMPOSE_FILE" run --rm prefect_cli prefect deployment run "Scraping Flow Deployment"

echo "Scraping flow has been triggered!"

# Display the status of the services
echo "Services status:"
docker-compose -f "$COMPOSE_FILE" ps
