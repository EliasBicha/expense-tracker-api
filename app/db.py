from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    # Keep bound values (e.g. password hashes, emails) out of SQL logs and error messages.
    hide_parameters=True,
    # Timestamps are stored as TIMESTAMPTZ; pinning the session time zone makes
    # PostgreSQL return them in UTC regardless of the server's local setting (D-10).
    connect_args={"options": "-c timezone=UTC"},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
