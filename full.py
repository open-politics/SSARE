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
        await client.get(f"{services['postgres_service']}/flags")

        # # Wait for flags to be produced - adjust sleep time as needed
        await asyncio.sleep(10)

        # Produce flags and trigger scraping
        await client.post(f"{services['scraper_service']}/create_scrape_jobs")

        # Wait for scraping to complete - adjust sleep time as needed
        await asyncio.sleep(15)

        # Store raw articles
        await client.post(f"{services['postgres_service']}/store_raw_articles")

        # Wait for raw articles to be stored - adjust sleep time as needed
        await asyncio.sleep(10)
        

        await client.post(f"{services['qdrant_service']}/create_embedding_jobs")

        # Wait for embedding jobs to be created - adjust sleep time as needed
        await asyncio.sleep(10)

        # Trigger Embedding Creation
        await client.post(f"{services['nlp_service']}/generate_embeddings", timeout=60)

        # Wait for embedding process - adjust sleep time as needed
        await asyncio.sleep(30)

        # Store Embeddings
        await client.post(f"{services['postgres_service']}/store_articles_with_embeddings")

        # Wait for embeddings to be stored - adjust sleep time as needed
        await asyncio.sleep(10)

        # Store Embeddings in Qdrant
        await client.post(f"{services['qdrant_service']}/store_embeddings")

        print("Test run complete. Check logs and database for results.")

# Run the test
asyncio.run(test_ssare_pipeline())
