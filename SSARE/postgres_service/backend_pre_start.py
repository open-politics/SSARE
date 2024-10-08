import logging
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import select
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed
from core.service_mapping import ServiceConfig
from sqlalchemy.orm import sessionmaker

config = ServiceConfig()

DATABASE_URL = (
    f"postgresql+asyncpg://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
    f"@articles_database:5432/{config.ARTICLES_DB_NAME}"
)

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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