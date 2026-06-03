"""Engine / session management and schema bootstrap."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from goldmind.config import get_settings
from goldmind.db.models import Base


@lru_cache(maxsize=1)
def get_engine(url: str | None = None) -> Engine:
    url = url or get_settings().database_url
    # pool_pre_ping avoids stale-connection errors on long-lived VPS processes.
    return create_engine(url, pool_pre_ping=True, future=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope: commit on success, rollback on error, always close."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    """Create tables from the ORM metadata (dev/test convenience; production uses
    schema.sql / Alembic migrations)."""
    Base.metadata.create_all(get_engine())
