from prefect import flow, get_run_logger
from prefect_ray import RayTaskRunner
from tasks.scraping_tasks import scrape_cnn_articles, scrape_dw_articles, scrape_bbc_articles
from tasks.processing_tasks import process_scraped_data
from tasks.redis_tasks import save_contents_to_redis
import pandas as pd
import os
SCRAPER_TASKS = {
    'cnn': scrape_cnn_articles,
    'dw': scrape_dw_articles,
    'bbc': scrape_bbc_articles,
}

task_runner = RayTaskRunner(
    address=os.getenv("RAY_ADDRESS"),
    init_kwargs={
        "runtime_env": {
            "working_dir": ".",  
            "pip": [
                "prefect",
                "prefect-ray",
                "newspaper3k",
                "aiohttp",
                "beautifulsoup4",
                "pandas",
                "redis",
                "lxml[html_clean]",
            ],
        }
    }
)

@flow(name="Scrape Sources Flow", task_runner=task_runner)
def scrape_sources_flow(flags: list):
    logger = get_run_logger()
    futures = []
    for flag in flags:
        if flag in SCRAPER_TASKS:
            task = SCRAPER_TASKS[flag]
            future = task.submit()
            futures.append(future)
            logger.info(f"Submitted scraper task for: {flag}")
        else:
            logger.warning(f"No scraper task found for flag: {flag}")
    results = [future.result() for future in futures]
    combined_df = pd.concat(results, ignore_index=True)
    contents = process_scraped_data(combined_df)
    save_contents_to_redis(contents)

if __name__ == "__main__":
    scrape_sources_flow.serve(
        name="scrape-sources-deployment",
        parameters={"flags": ["cnn", "dw", "bbc"]},
        cron="0 * * * *"
    )