from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel
from .service_mapping import config
from contextlib import asynccontextmanager

def get_db_url():
    if config.DB_MODE == "managed":
        host = config.MANAGED_ARTICLES_DB_HOST
        port = config.MANAGED_ARTICLES_DB_PORT
    else:
        host = "articles_database"
        port = config.ARTICLES_DB_PORT

    return (
        f"postgresql+asyncpg://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
        f"@{host}:{port}/{config.ARTICLES_DB_NAME}"
    )

DATABASE_URL = get_db_url()

engine = create_async_engine(DATABASE_URL, echo=False)

@asynccontextmanager
async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)