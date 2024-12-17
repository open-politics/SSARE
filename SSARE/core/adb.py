from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel
from .service_mapping import config, get_db_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
import logfire

logfire.configure()
logfire.instrument_asyncpg()

DATABASE_URL = get_db_url()

engine = create_async_engine(DATABASE_URL, echo=False)

async_session = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session

    
def get_redis_url():
    if config.REDIS_MODE == "managed":
        return f"redis://{config.MANAGED_REDIS_HOST}:{config.MANAGED_REDIS_PORT}"
    else:
        return f"redis://redis:{config.REDIS_PORT}"