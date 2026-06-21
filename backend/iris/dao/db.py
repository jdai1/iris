"""SQLAlchemy engine, base model, and ambient session management."""

from __future__ import annotations

from contextvars import ContextVar
from contextlib import contextmanager
from threading import local
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from iris.services.common.config import database_url


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""

    pass


engine = create_engine(database_url(), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
_session_var: ContextVar[Session | None] = ContextVar("iris_current_session", default=None)
_session_state = local()


def init_db() -> None:
    """Create all known tables for the configured database."""
    from iris import models  # noqa: F401

    Base.metadata.create_all(engine)
    ensure_user_auth_columns()


def ensure_user_auth_columns() -> None:
    """Add auth identity columns when an existing DB predates Firebase auth."""
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    dialect = engine.dialect.name
    statements: list[str] = []

    if dialect == "sqlite":
        if "firebase_uid" not in columns:
            statements.append("ALTER TABLE users ADD COLUMN firebase_uid VARCHAR(128)")
        if "photo_url" not in columns:
            statements.append("ALTER TABLE users ADD COLUMN photo_url TEXT")
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_firebase_uid ON users (firebase_uid)"
        )
    elif dialect == "postgresql":
        if "firebase_uid" not in columns:
            statements.append("ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid VARCHAR(128)")
        if "photo_url" not in columns:
            statements.append("ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url TEXT")
        statements.append(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_firebase_uid ON users (firebase_uid)"
        )
    else:
        return

    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


@contextmanager
def session_scope() -> Iterator[Session]:
    """Open a transaction-scoped session and bind it as the current session."""
    init_db()
    session = SessionLocal()
    token = _session_var.set(session)
    previous_thread_session = getattr(_session_state, "session", None)
    _session_state.session = session
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        try:
            _session_var.reset(token)
        except ValueError:
            pass
        _session_state.session = previous_thread_session
        session.close()


@contextmanager
def bind_session(session: Session) -> Iterator[Session]:
    """Temporarily bind an externally managed session as the current session."""
    token = _session_var.set(session)
    previous_thread_session = getattr(_session_state, "session", None)
    _session_state.session = session
    try:
        yield session
    finally:
        try:
            _session_var.reset(token)
        except ValueError:
            pass
        _session_state.session = previous_thread_session


def current_session() -> Session:
    """Return the session bound to the current thread."""
    session = _session_var.get() or getattr(_session_state, "session", None)
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
