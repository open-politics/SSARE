#!/bin/bash
# List all services, exclude those starting with 'flow-'
services=$(docker compose config --services | grep -v '^flow-')

# Run docker-compose up with the list of non-flow services
docker compose up --build $services