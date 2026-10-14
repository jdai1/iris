import pytest
from sqlalchemy import create_engine

from iris.services.common.config import database_url


@pytest.mark.parametrize("scheme", ["postgres", "postgresql"])
def test_database_url_uses_installed_postgres_driver(monkeypatch, scheme):
    monkeypatch.setenv("DATABASE_URL", f"{scheme}://user:password@example.com:5432/iris")

    assert database_url() == "postgresql+psycopg2://user:password@example.com:5432/iris"
    engine = create_engine(database_url())  # Imports driver without connecting.
    assert engine.dialect.driver == "psycopg2"
    engine.dispose()


@pytest.mark.parametrize("url", ["sqlite:///:memory:", "postgresql+psycopg://user:password@example.com/iris"])
def test_database_url_preserves_explicit_driver(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    assert database_url() == url
