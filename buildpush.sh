#!/bin/bash:ssare/build-and-push.sh
#!/bin/bash

# Namespace
NAMESPACE=ssare

# Registry
REGISTRY=open-politics-project

# Ensure you're logged in
echo "Logging into Docker Registry..."
docker login || { echo "Docker login failed"; exit 1; }

# List of services to build and push
services=(
  classification_service
  embedding_service
  entity_service
  geo_service
  main_core_app
  ollama
  postgres_service
  scraper_service
  ray_head
  ray_worker
)

# Build and push each service
for service in "${services[@]}"; do
  DOCKERFILE="./SSARE/${service}/Dockerfile"
  
  if [ -f "$DOCKERFILE" ]; then
    echo "Building image for $service..."
    docker build -t ${REGISTRY}/${service}:latest -f "$DOCKERFILE" ./SSARE

    echo "Pushing image ${REGISTRY}/${service}:latest..."
    docker push ${REGISTRY}/${service}:latest

    echo "$service image built and pushed successfully."
    echo "-------------------------------------------"
  else
    echo "Dockerfile for $service not found at $DOCKERFILE. Skipping..."
    echo "-------------------------------------------"
  fi
done

echo "All applicable images have been built and pushed."
