# Opol Stack

Welcome to the Opol Stack documentation!

This guide provides an overview of the services, tasks, and flows used to orchestrate this data operation. Whether you're a developer looking to contribute or an enthusiast eager to understand the system, this documentation aims to help you navigate and comprehend the architecture effectively.

If something is unclear, missing documentation, or unnecessarily hard to get into, please let us know via a GitHub Issue.

## Table of Contents
- Overview
- Directory Structure
- Environment Configuration
- Service Orchestration
  - Docker Files
  - Core Services
  - Flow Services
- Flow Orchestration
  - List of Flows & Pipelines
- Service Configuration
- Observability
- Setup and Deployment
- Contribution Guidelines
- Resources

## Overview
The `opol/opol/stack` directory is the heart of the application, responsible for orchestrating various microservices and workflows essential for the system's functionality. This folder is ready to use with docker compose for local development.

*In it's advanced form it is deployed as a kubnetes cluster deployed with helm. For more information look into [here](../../.deployment)*

## Directory Structure

| File/Directory          | Description                                                                 |
|-------------------------|-----------------------------------------------------------------------------|
| **README.md**           | You are here                                                                |
| **.store**             | Store for scraped data, geocoding data, and redis queue storage              |
| **compose.local.yml**   | Compose File using a local Prefect server                                    |
| **compose.yml**         | Development Compose File                                                    |
| **flows.compose.yml**   | Compose File for flows                                                     |
| **prefect.yaml**        | Prefect Configuration File                                                |
| **core**                | Service package, holding pydantic models, URL mappings, database connections |
| **flows**               | Batch processing flows: scraping, geocoding, entities, classification, embeddings |
| **services**            | Services, mostly used for live requests: scraping, geocoding, embeddings .. + a dashboard |

## Environment Configuration
Environment variables are managed through the `.env` file, which is essential for configuring service parameters like API keys, database credentials, and service ports. The `.env.example` file serves as a template, outlining the required variables without exposing sensitive information. Ensure you populate the `.env` file with the necessary configurations before deploying the stack.
```bash
mv opol/stack/.env.example opol/stack/.env
```
| This stack is currently using a few providers like Huggingface & Prefect. But they are generally free to use. For a workaround with huggingface the ollama container could be used to generate inference embeddings. Prefect can be self-hosted `compose.local.yml`

## Service Orchestration

### Docker Compose Files
The stack utilizes Docker Compose to manage and orchestrate multiple services seamlessly.
- `compose.yml`: Defines the production-ready services, configurations, and dependencies.
- `compose.local.yml`: Environment-specific compose file for local development.
- `flows.compose.yml`: Compose File for flows 

# Flows
If you boot up the stack, the prefect worker will start up and create a workpool. With the deploy-flows.sh:
```bash
bash deploy-flows.sh
```
You can deploy, i.e. register the flow. If the cron scedule in the prefect.yaml is hit the flow run. It can also be triggered via cli. Which is e.g. what the core-app does to trigger the flows. The max-concurrent setting limits the number of concurrent runs.
Some flows have specific dependencies, all of this is managed in the flows. The lightweight flows use the worker-base image.

For local development the flows.compose.yml is used:
```bash
docker compose -f flows.compose.yml up flow-embeddings --build
```



### Core Services
Core services form the backbone of the application, handling functionalities like data scraping, engineering, batch processing and various utitlies centered around opol.

| All these services and packages build services with shared modules from `core`. \
| Here you can find the shared pydantic models, service-url-mappings, database connections and more.

| The data scraped is stored in .store


Databases & Queues:
- PostgreSQL Database (`database-articles`)
- Redis Server (`redis`)
- Prefect Server (`prefect_server`)

Services:
- Opol Dashboard/ Core App (`app`)
- Scraping Service (`scraping_service`)
- Geocoding Service (`geocoding_service`)
- Embeddings Service (`embedding_service`)
- Entities Service (`entities_service`)
- Classification Service (`classification_service`)

Utilities:
- Ollama Server (`ollama`) # For local LLMs
- Pelias Placeholder (`pelias_placeholder`) # For local geocoding
- SearXng # Self hostable search engine for many popular providers (Arxiv, DuckDuckGo)


### Flows

Flows are responsible for managing batch processing tasks, such as ingesting and processing news data, as well as handling repetitive lightweight jobs.

#### Main Ingestion Flow

The primary ingestion flow follows this sequence:

1. **Scraping** 
2. **Embeddings** 
3. **Entities** 
4. **Geocoding** 
5. **Classification** 
6. **Completion** ✅

#### Flow Mechanics

Each flow operates uniformly with the following steps:

- **Postgres Service Endpoints:**
  1. **Create Jobs:** Push jobs to the Redis queue `unprocessed_**pipeline_name**`.
  2. **Save Results:** Retrieve results from the Redis queue `processed_**pipeline_name**`.

These pipelines effectively decouple container interactions, ensuring smooth operation.

#### Flow Execution

- Each flow is initiated within containers, launching a long-running Prefect `serve` deployment.
- Upon triggering (via HTTP API or Prefect command), the flow checks Redis for pending jobs and processes them accordingly.

#### Orchestration Flow

The orchestration flow is crucial for:

- **Triggering Jobs:** Initiates job creation via HTTP endpoints.
- **Processing:** Manages the processing sequence.
- **Saving:** Ensures results are saved post-processing.

**Example Orchestration Sequence:**

1. **Trigger:** Orchestration Flow initiates.
2. **Job Creation:** Postgres Service creates embedding jobs for content lacking embeddings.
3. **Queue Management:** 
   - Redis Queue receives content without embeddings.
   - Embedding Flow processes and updates the queue with content containing embeddings.
4. **Result Saving:** Postgres Service saves the processed embeddings.



This orchestration flow acts as an overcomplicated cron job, But it allows the flexibility to dynamically add more comprehensive orchestration mechanisms through HTTP requests.


## Flow Orchestration
Flows are defined using Prefect, enabling asynchronous and structured workflow management.

Read more in the flows [README](flows/README.md)

## Observability
Prefect provides observability features, offering insights into task execution and resource orchestration.

## Setup and Deployment

### Prerequisites
- Docker: Ensure Docker is installed on your system.
- Docker Compose: Required for orchestrating services.

### Steps
1. Clone the Repository
2. Configure Environment Variables
   - Duplicate `.env.example` to `.env`
   - Populate the `.env` file with necessary values.
3. Build and Start Services
   - For local development: `docker compose -f compose.local.yml up --build`
   - For production: `docker compose -f compose.yml up --build`
4. Access Services
   - Core App: `http://localhost:8089`

Now you can use opol via the self-hosted stack!

Just change in your code:
```python
from opol import OPOL

opol = OPOL()

# to

opol = OPOL(mode="local)
```
And the client is ready to use. \
Just give it some time to populate the data. For every 10 sources specified it should take about 20 Minutes to load everything into system (on a 32GB Ram Machine).



## Resources
- Prefect Documentation: [https://docs.prefect.io/](https://docs.prefect.io/)
- Docker Documentation: [https://docs.docker.com/](https://docs.docker.com/)
- SQLModel Documentation: [https://sqlmodel.tiangolo.com/](https://sqlmodel.tiangolo.com/)
- Open Politics Documentation: [https://docs.open-politics.org/](https://docs.open-politics.org/) (But this documentation in the repo here is always newer)

