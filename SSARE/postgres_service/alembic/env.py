from sqlalchemy import engine_from_config, pool
from alembic import context
from sqlmodel import SQLModel
from core.service_mapping import ServiceConfig
from core.models import Content

config = ServiceConfig()

DATABASE_URL = (
    f"postgresql+psycopg2://{config.ARTICLES_DB_USER}:{config.ARTICLES_DB_PASSWORD}"
    f"@articles_database:5432/{config.ARTICLES_DB_NAME}"
)

target_metadata = SQLModel.metadata


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


def run_migrations_online():
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        {"sqlalchemy.url": DATABASE_URL},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()