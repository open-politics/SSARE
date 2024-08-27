from logging.config import fileConfig
from sqlalchemy import engine_from_config, create_engine
from sqlalchemy import pool
from alembic import context
from sqlmodel import SQLModel
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.service_mapping import ServiceConfig
from core.models import Article

config = ServiceConfig()

DATABASE_URL = (
    f"postgresql://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
    f"@articles_database:5432/{config.ARTICLES_DB_NAME}"
)

target_metadata = SQLModel.metadata

def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    configuration = context.config
    configuration.set_main_option("sqlalchemy.url", DATABASE_URL)
    connectable = engine_from_config(
        configuration.get_section(configuration.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()