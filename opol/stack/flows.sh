#!/bin/bash
# Get all services starting with 'flow-' from the docker-compose.yml
services=$(docker compose config --services | grep '^flow-')

# Run docker-compose up with the list of services
docker compose up --build $services