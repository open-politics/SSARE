This directory contains the following components:

- `dockerfiles/`: A collection of Dockerfiles for our services.
- `python-client/`: A Python client for seamless interaction with our API.
- `stack/`: Our services configured in a Docker Compose setup for local execution.

Within the `stack` directory, you will find the majority of the relevant code for the services.

This setup is a microservice architecture consisting of FastAPI servers and Prefect flows, enabling the complete deployment of Opol on a local machine.

Dependencies are domain-specific and are separated into shared Dockerfiles. For example, the Embedding Service (for real-time embedding creation) and the Prefect embedding flow (for batch embedding creation) are both built from the same Dockerfile and directory (/embedding-service). 

Prefect is used to organize data pipelines & operations into orchestrated flows. Their tasks (from execution, retrying and logging) are automatically handled within Prefects's ressouce allocation capabilities. From local execution to large scale orchestration, Prefect is the backbone of our orchestration layer.

For lightweight flows (such as fetching and modifying text pages), simple background tasks are executed using Prefect workers.

Heavier flows are managed with separate Dockerfiles and are executed using the RayTaskRunner in Prefect, which employs Ray worker nodes for parallel execution.

While this may not provide a direct advantage on smaller machines where heavy parallel execution is unnecessary, it supports two beneficial patterns:
- Scaling up processing power by spawning additional Ray workers (adjust the `replicas` value in the compose file).
- Utilizing common resource pools to which tasks are assigned.