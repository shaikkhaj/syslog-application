"""Database bootstrap: wait for the DB, create tables, seed reference data."""

import logging
import time

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import Base, SessionLocal, engine
from app.models.models import EventType  # noqa: F401  (registers models on Base)
from app.models.notification import Notification, NotificationSettings  # noqa: F401 (registers models on Base)
from app.syslog.event_types import EVENT_TYPE_SEEDS

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 30
_RETRY_DELAY_SECONDS = 1.0


def wait_for_database(max_attempts: int = _MAX_ATTEMPTS) -> bool:
    """Block until the database accepts connections (used on startup)."""
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:  # pragma: no cover - exercised in real DB runs
            logger.warning(
                "Database not ready (attempt %s/%s): %s",
                attempt,
                max_attempts,
                exc.__class__.__name__,
            )
            time.sleep(_RETRY_DELAY_SECONDS)
    return False


def seed_event_types(session: Session) -> None:
    """Sync the event-type catalog with the seeds (idempotent).

    Adds missing codes and prunes rows that are no longer part of the
    taxonomy (the Phase 2 rename left stale lowercase codes on pre-existing
    development databases).
    """
    from sqlalchemy import select

    existing = {row.code: row for row in session.execute(select(EventType)).scalars()}
    seed_codes = {seed["code"] for seed in EVENT_TYPE_SEEDS}
    added = 0
    for seed in EVENT_TYPE_SEEDS:
        if seed["code"] not in existing:
            session.add(EventType(**seed))
            added += 1
    pruned = 0
    for code, row in existing.items():
        if code not in seed_codes:
            session.delete(row)
            pruned += 1
    session.commit()
    if added:
        logger.info("Seeded %s event types into the catalog", added)
    if pruned:
        logger.info("Pruned %s obsolete event types from the catalog", pruned)


def _migrate_missing_columns() -> None:
    """Best-effort column migrations for databases created before Phase 4."""
    from sqlalchemy import inspect as sa_inspect

    inspector = sa_inspect(engine)
    if "devices" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("devices")}
    if "device_type" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE devices ADD COLUMN device_type VARCHAR(32) "
                    "DEFAULT 'router'"
                )
            )
        logger.info("Migrated devices table: added device_type column")


def init_db() -> None:
    """Full startup initialisation. Safe to run repeatedly."""
    if not wait_for_database():
        raise RuntimeError(
            "Could not connect to the database after "
            f"{_MAX_ATTEMPTS} attempts — aborting startup"
        )
    Base.metadata.create_all(bind=engine)
    _migrate_missing_columns()
    with SessionLocal() as session:
        seed_event_types(session)
    logger.info("Database initialised (tables created, event types seeded)")
