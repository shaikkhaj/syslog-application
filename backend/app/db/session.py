"""SQLAlchemy engine, session factory and declarative base."""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()
DATABASE_URL = settings.build_database_url()

_engine_kwargs: dict = {"future": True, "pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    # SQLite is only used by the automated tests; it must be shareable
    # across FastAPI's dependency threads.
    _engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **_engine_kwargs)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_db():
    """FastAPI dependency that yields a scoped session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
