# SSARE: Semantic Search Article Recommendation Engine
Up-to-date political news RAG endpoint for semantic search and article recommendations.

![SSARE](media/banner.jpg)

## Introduction
SSARE stands for Semantic Search Article Recommendation Engine, an open-source platform that comfortably orchestrates scraping, processing into vector representations and querying of news articles. 

SSARE serves as an efficient and scalable resource for semantic search and article recommendations, catering primarily to news data.

SSARE is an always up to date political news RAG endpoint.

The engine is adaptable to various sources, requiring only a sourcing cript that outputs the data in the format of a dataframe with the columns "url," "headline," and "paragraphs." Once integrated, SSARE processes these articles using embeddings models of your choice(upcoming, currently hardcoded), stores their vector representations in a Qdrant vector database, and maintains a full in a PostgreSQL database. 

SSARE is a composition of microservices to make this project a scalable and maintainable solution. The services are:


## Version 1 Deployment
We are excited to announce that SSARE version 1 is now operational and usable!

### Getting Started
Ensure Docker and docker-compose are installed. 
Then:
1. Download the source code by cloning the repository.
    ```bash
    git clone https://github.com/JimVincentW/SSARE.git
    ``` 
2. Initiate the setup:
   ```bash
   cd SSARE
   docker-compose up --build
   ```
3. Execute the initial setup script:
   ```bash
   python full.py
   ```
   Wait
4. Query the API:
   ```bash
   curl -X GET "http://127.0.0.1:6969/search?query=Argentinia&top=5"
   ```

The design philosophy underscores flexibility, allowing integration with any scraper script that aligns with the specified data structure. The infrastructure benefits from each additional source, enriching the system's capability to amass, store, and retrieve news content efficiently.

## Upcoming Features

### Future Roadmap
The project's trajectory includes plans for enhanced service orchestration (with Kubernetes) and expanded scraper support, all aimed at bolstering the engine's functionality and reach.

### Participation: Script Contributions
We welcome contributions from passionate activists, enthusiastic data scientists, and dedicated developers. Your expertise can greatly enhance our repository, expanding the breadth of our political news coverage. Join us in shaping the future of SSARE and making a meaningful impact on the world of news analysis and recommendation systems. Together, let's create a platform that empowers individuals to stay informed and engaged. 

## Practical Instructions
Here's a concise guide to utilizing SSARE:

- Deploy and construct the environment using:
  ```bash
  docker-compose up --build
  ```
- Verify service functionality:
  ```bash
  python full.py
  ```
- For custom scraper integration, scripts should yield "url," "headline," and "paragraphs." Store your script at:
  ```
  SSARE/scraper_service/scrapers
  ```
  Update the scraper configuration accordingly:
  ```
  SSARE/scraper_service/scrapers/scrapers_config.json
  ```
  The orchestration service will process your script once implemented.

If your additional scripts need scraping libraries other than BeautifulSoup, please add them to the requirements.txt file in the scraper_service folder (and create a pull request).

## Important Notes
Current limitations include the pending development of the scraper service and orchestration framework, alongside the unavailability of postgres database querying features. However, individual API endpoints remain accessible.

## Architecture and Storage
SSARE's architecture fosters communication through a decoupled microservices design, ensuring scalability and maintainability. The system is composed of the following services:
- [] (details to be added)

The scrape jobs are created with Celery. 

Regarding storage, SSARE employs PostgreSQL for data retention and Qdrant for semantic recommendations, ensuring a robust and responsive search and retrieval system.

## Licensing
SSARE is distributed under the MIT License, with the license document available for reference within the project repository.