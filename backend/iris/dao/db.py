"""SQLAlchemy engine, base model, and ambient session management."""

from __future__ import annotations

from contextlib import contextmanager
from threading import local
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from iris.services.common.config import database_url


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""

    pass


engine = create_engine(database_url(), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
_session_state = local()


def init_db() -> None:
    """Create all known tables for the configured database."""
    from iris import models  # noqa: F401

    Base.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Open a transaction-scoped session and bind it as the current session."""
    init_db()
    session = SessionLocal()
    previous = getattr(_session_state, "session", None)
    _session_state.session = session
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _session_state.session = previous
        session.close()


@contextmanager
def bind_session(session: Session) -> Iterator[Session]:
    """Temporarily bind an externally managed session as the current session."""
    previous = getattr(_session_state, "session", None)
    _session_state.session = session
    try:
        yield session
    finally:
        _session_state.session = previous


def current_session() -> Session:
    """Return the session bound to the current thread."""
    session = getattr(_session_state, "session", None)
    if session is None:
        raise RuntimeError("no active Iris database session")
    return session


def flush() -> None:
    """Flush pending writes in the current session."""
    current_session().flush()


def commit() -> None:
    """Commit the current session."""
    current_session().commit()


def rollback() -> None:
    """Roll back the current session."""
    current_session().rollback()
