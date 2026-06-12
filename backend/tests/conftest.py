from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from iris.dao import db
from iris.dao.db import Base


@pytest.fixture()
def session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db.engine = engine
    db.SessionLocal.configure(bind=engine)
    Base.metadata.create_all(engine)
    with Session(engine, future=True) as session:
        yield session
