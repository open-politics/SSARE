# SSARE
Semantic Search Article Recommendation Engine

![Alt text](media/image.png)

## Overview
SSARE (Semantic Searcg Article Recommendation Engine) is an advanced, open-source information architecture designed to autonomously aggregate, process, and store news articles. With a focus on political discourse, SSARE aligns with the upcycling philosophy of data, enabling efficient, on-demand retrieval of pertinent information.

## Contribution: Article Input Scripts
We are actively seeking contributions from data scientists and coders, particularly in the realm of article input scripts. By writing scripts that scrape, process, and standardize news articles, you can help us expand our database and improve the breadth of our political news coverage.


## Usage
run and build with docker-compose
```
Run full.py to test the services.
If you have a scraper script, the expected format are the columns: url, headline, paragraphs.
Put the script into 
SSARE/scraper_service/scrapers
and add the location to the config at
SSARE/scraper_service/scrapers/scrapers_config.json.

## Note
The scraper service is not yet round. The orchestration service not written.
Querying is the databases is not yet implemented.

## Storage
The storage is postgresql and qdrant. Both can be used to retrieve/ query.
Suggestion right now: recommend with qdrant, deliver with postgres.

## Architecture
The services communicate with api calls and data is pushed to redis queues. 
A more detailed description will follow.


## License
SSARE is licensed under the MIT License - see the LICENSE file for details.