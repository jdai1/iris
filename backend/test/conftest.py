from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.db as db
from app.models.mixins import Base
from test.factories import (
    DomainFactory,
    DomainMappingFactory,
    EntryFactory,
    LinkFactory,
    LinkMappingFactory,
)


@pytest.fixture(scope="session")
def db_engine():
    """Create database engine and tables for the test session."""
    # Create pgvector extension if it doesn't exist
    with db.engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(db.engine)
    yield db.engine
    Base.metadata.drop_all(db.engine)


@pytest.fixture(scope="session")
def db_connection(db_engine):
    """Create a connection and start a transaction for the test session."""
    connection = db_engine.connect()
    transaction = connection.begin()
    yield connection
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def db_session(db_connection):
    """Create a database session with savepoint for each test.

    Patches db.session so all app code uses this test session.
    """
    # Create a savepoint for this test
    savepoint = db_connection.begin_nested()

    # Create a session bound to the connection
    session = Session(bind=db_connection)

    # Set session for factories
    DomainFactory._meta.sqlalchemy_session = session
    LinkFactory._meta.sqlalchemy_session = session
    EntryFactory._meta.sqlalchemy_session = session
    LinkMappingFactory._meta.sqlalchemy_session = session
    DomainMappingFactory._meta.sqlalchemy_session = session

    # Patch db.session so app code uses this test session
    with patch.object(db, "session", session):
        try:
            yield session
        finally:
            session.close()
            savepoint.rollback()

            DomainFactory._meta.sqlalchemy_session = None
            LinkFactory._meta.sqlalchemy_session = None
            EntryFactory._meta.sqlalchemy_session = None
            LinkMappingFactory._meta.sqlalchemy_session = None
            DomainMappingFactory._meta.sqlalchemy_session = None
