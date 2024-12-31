import logging
import asyncio
import os

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import select
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed
from core.service_mapping import config, get_db_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from core.utils import logger


DATABASE_URL = get_db_url()

logger.info(f"DATABASE_URL: {DATABASE_URL}")
logger.info(f"DB_MODE: {os.getenv('DB_MODE')}")

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)



max_tries = 60 * 5  # 5 minutes
wait_seconds = 1


@retry(
    stop=stop_after_attempt(max_tries),
    wait=wait_fixed(wait_seconds),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARN),
)
async def init() -> None:
    try:
        async with async_session() as session:
            # Create vector extension first
            await session.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
            # Create trigram extension
            await session.execute(text('CREATE EXTENSION IF NOT EXISTS pg_trgm;'))
            await session.commit()
            # Then check connection
            await session.execute(select(1))
    except Exception as e:
        logger.error(e)
        raise e


async def main() -> None:
    logger.info("Initializing service")
    await init()
    logger.info("Service finished initializing")


if __name__ == "__main__":
    asyncio.run(main())