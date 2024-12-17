from sqlalchemy import engine_from_config, pool
from alembic import context
from app.core.models import SQLModel
from app.core.service_mapping import config, get_sync_db_url
import os
import logging
import pgvector
from logging.config import fileConfig

# config = context.config
# fileConfig(config.config_file_name)

# config = ServiceConfig()

DATABASE_URL = get_sync_db_url()

target_metadata = SQLModel.metadata
logger = logging.getLogger('alembic')
logger.info("target_metadata: %s", target_metadata)


def run_migrations_offline():
    """Run migrations in 'offline' mode."""
    url = DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with vector type support."""
    # Add the 'vector' type to the dialect's ischema_names
    connection.dialect.ischema_names['vector'] = pgvector.sqlalchemy.Vector

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        {"sqlalchemy.url": DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
