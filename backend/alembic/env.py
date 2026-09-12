"""Alembic environment (PRD 0, section 30).

Every schema change is migration-driven. The database URL comes from the
application settings rather than alembic.ini, so there is exactly one place
that knows how to reach the database and no credentials sit in a tracked file.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

# Importing the model package populates Base.metadata, which is what
# autogenerate compares the live database against.
import app.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, via ``alembic upgrade --sql``."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection.

    The engine is built straight from the settings URL. Passing the URL through
    alembic.ini would route it via configparser, where a ``%`` in a password
    becomes an interpolation error.
    """
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
