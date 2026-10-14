"""Optional integration check against a disposable local pgvector database.

Set IRIS_TEST_POSTGRES_URL to a local test database. Uses a rolled-back transaction.
"""
import os

import pytest
from iris.dao import db, search
from iris.dao.sources import get_or_create_source
from iris.models import Document
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@pytest.mark.skipif(not os.getenv("IRIS_TEST_POSTGRES_URL"), reason="requires disposable local pgvector")
def test_postgres_bounded_retrieval():
    engine = create_engine(os.environ["IRIS_TEST_POSTGRES_URL"])
    assert engine.url.host in {"localhost", "127.0.0.1"}, "Only use a local test database"
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Isolated namespace; rolling back also removes these tables.
            connection.execute(text("CREATE SCHEMA iris_bounded_search_test"))
            connection.execute(text("SET LOCAL search_path TO iris_bounded_search_test, public"))
            db.Base.metadata.create_all(connection)
            with Session(bind=connection) as session, db.bind_session(session):
                source = get_or_create_source("https://test.invalid", status="indexed")
                for i in range(35):
                    session.add(Document(
                        source_id=source.id, url=f"https://test.invalid/{i}",
                        title=f"Small teams {i}", extracted_text="coordination", category="software",
                        document_type="essay", crawl_status="fetched",
                        topics=["Teams"] if i % 2 else None,
                        embedding_vector=[1.0] + [0.0] * 1535,
                    ))
                session.flush()
                assert len(search.keyword_search_documents({"small", "teams"}, limit=3)) == 3
                assert len(search.tag_search_documents({"teams"}, limit=3)) == 3
                assert len(search.category_search_documents({"software"}, limit=3)) == 3
                assert len(search.semantic_search_documents([1.0] + [0.0] * 1535, limit=3)) == 3
                assert search.keyword_search_documents({"no-match"}, limit=3) == []
                assert search.tag_search_documents({"team"}, limit=3) == []
        finally:
            transaction.rollback()
    engine.dispose()
