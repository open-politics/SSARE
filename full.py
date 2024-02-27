import httpx
import asyncio
import json

async def test_ssare_pipeline():
    base_url = "http://localhost"  # Replace with actual host if different
    services = {
        "scraper_service": f"{base_url}:8081",
        "nlp_service": f"{base_url}:0420",
        "postgres_service": f"{base_url}:5434",
        "qdrant_service": f"{base_url}:6969",
        # Add other services as needed
    }

    async with httpx.AsyncClient() as client:

        # Produce flags
        flags_result = await client.get(f"{services['postgres_service']}/flags")
        if flags_result.status_code == 200:
            print("Flags produced successfully")
        else:
            print("Failed to produce flags")

        # Wait for flags to be produced - adjust sleep time as needed
        await asyncio.sleep(10)

        # Produce flags and trigger scraping
        await client.post(f"{services['scraper_service']}/create_scrape_jobs")
        print("Scrape jobs created")

        # Wait for scraping to complete - adjust sleep time as needed
        await asyncio.sleep(20)
        # Store raw articles
        await client.post(f"{services['postgres_service']}/store_raw_articles")
        print("Raw articles stored")

        # Wait for raw articles to be stored - adjust sleep time as needed
        await asyncio.sleep(10)
        
        # Create embedding jobs
        embedding_jobs_result = await client.post(f"{services['postgres_service']}/create_embedding_jobs")
        if embedding_jobs_result.status_code == 200:
            print("Embedding jobs created successfully")
        else:
            print("Failed to create embedding jobs")

        # Wait for embedding jobs to be created - adjust sleep time as needed
        await asyncio.sleep(10)

        # Trigger Embedding Creation
        await client.post(f"{services['nlp_service']}/generate_embeddings", timeout=70)
        print("Embeddings generated")

        # Wait for embedding process - adjust sleep time as needed
        await asyncio.sleep(30)

        # Store Embeddings
        await client.post(f"{services['postgres_service']}/store_articles_with_embeddings")
        print("Articles with embeddings stored")

        # Wait for embeddings to be stored - adjust sleep time as needed
        await asyncio.sleep(10)


        # Trigger pushing articles to queue in PostgreSQL service
        await client.post(f"{services['postgres_service']}/trigger_qdrant_queue_push")
        print("Articles pushed to queue in PostgreSQL service")

        # Wait for articles to be pushed to queue - adjust sleep time as needed
        await asyncio.sleep(2)

        # Trigger reading articles from queue in Qdrant service
        await client.post(f"{services['qdrant_service']}/store_embeddings")
        print("Articles read from queue in Qdrant service")

        print("Test run complete. Check logs and database for results.")
        qdrant_service_url = 'http://127.0.0.1:6969/search'

        test_query = "Germany"

        response = httpx.get(
            qdrant_service_url,
            params={
                "query": test_query, 
                "top": 5,
            }
        )

        result = response.json()[0]["payload"]
        prettified_result = json.dumps(result, indent=4)
        print(prettified_result)
        

# Run the test
asyncio.run(test_ssare_pipeline())
