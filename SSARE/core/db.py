from sqlmodel import Session, create_engine, select
from .models import Article
from .service_mapping import config

DATABASE_URL = (
    f"postgresql+asyncpg://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
    f"@articles_database:5432/{config.ARTICLES_DB_NAME}"
)

engine = create_engine(DATABASE_URL)

def init_db(session: Session) -> None:
    from sqlmodel import SQLModel
    session.exec(text('CREATE EXTENSION IF NOT EXISTS vector'))
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    
