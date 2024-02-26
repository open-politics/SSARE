import httpx
import asyncio

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
        embedding_jobs_result = await client.post(f"{services['qdrant_service']}/create_embedding_jobs")
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

        # Store Embeddings in Qdrant
        store_embeddings_result = await client.post(f"{services['qdrant_service']}/store_embeddings")
        if store_embeddings_result.status_code == 200:
            print("Embeddings stored in Qdrant successfully")
        else:
            print("Failed to store embeddings in Qdrant")

        print("Test run complete. Check logs and database for results.")

# Run the test
asyncio.run(test_ssare_pipeline())
