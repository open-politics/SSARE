## Directory Components

This directory contains the following components:

- **[Python Client](python-client)**: 
  This folder packages and abstracts the APIs of the **stack** into meaningful and semantically separated Python functions.
  The Python client builds the URL and fetches the endpoint for HTTP requests to the services (stack/services).

- **[Stack](stack)**:
  This folder contains the services that constitute the core logic of the application.
  Here lies the microservices application that constitutes the capabilities of Opol.
  The data of the stack is also placed here in `.store` (backups, credentials, data such as articles, geocoding, and Redis).