from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlmodel import SQLModel
from .service_mapping import config
from contextlib import asynccontextmanager

DATABASE_URL = (
    f"postgresql+asyncpg://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
    f"@articles_database:5432/{config.ARTICLES_DB_NAME}"
)

engine = create_async_engine(DATABASE_URL, echo=False)

@asynccontextmanager
async def get_session() -> AsyncSession:
    async with AsyncSession(engine) as session:
        yield session

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)