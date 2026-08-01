from iris.services.common.config import database_url


def test_database_url_normalizes_legacy_postgres_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://user:password@example.com:5432/iris")

    assert database_url() == "postgresql://user:password@example.com:5432/iris"
