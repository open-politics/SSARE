
## Directory Components

This directory contains the following components:

- **_dockerfiles/**: 
  - Contains shared Dockerfiles and requirements for building base images.
  - Includes files like `RayBase.Dockerfile` and `raybaserequirements.txt` to ensure a consistent environment across services and flows.

- **compose.local.yml & compose.yml**: 
  - Docker Compose files for configuring and running the entire stack locally.
  - Facilitates easy orchestration of services and flows.

- **core/**: 
  - A collection of shared modules and configurations.
  - Includes database connections, middleware, and utility functions used across different services and flows.

- **flows/**: 
  - Contains Prefect flow definitions and Dockerfiles for each flow.
  - Each subdirectory (e.g., classification, embeddings, entities) includes a Dockerfile and flow scripts for batch processing and task orchestration.

- **services/**: 
  - Houses the microservices, each with its own directory.
  - Each directory contains a Dockerfile, service-specific scripts, and configuration files.
  - Services are built using FastAPI and handle real-time operations.

## Prefect for Orchestration

- Prefect is used to organize data pipelines and operations into orchestrated flows.
- It manages task execution, retrying, and logging, leveraging Prefect's resource allocation capabilities.
- Prefect serves as the backbone of the orchestration layer, from local execution to large-scale orchestration.

## Flow Execution

- Lightweight flows, such as fetching and modifying text pages, are executed using Prefect workers.
- Heavier flows are managed with separate Dockerfiles and executed using the RayTaskRunner in Prefect, which utilizes Ray worker nodes for parallel execution.

## APIs & Services

- APIs are built using FastAPI and are responsible for real-time operations.
- Services are built using FastAPI and are responsible for real-time operations.
