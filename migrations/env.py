from alembic import context
from sqlalchemy import create_engine, pool

from app.config import get_settings
from app.db import Base
import app.models  # noqa: F401  (registers the models on Base.metadata)

# Logging is intentionally not configured here: logging.config.fileConfig would
# disable the application's loggers when migrations run inside the test session.
target_metadata = Base.metadata


def run_migrations() -> None:
    engine = create_engine(get_settings().database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
