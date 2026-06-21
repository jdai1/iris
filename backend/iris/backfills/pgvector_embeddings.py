"""Create and backfill the optional pgvector embedding mirror column."""

from __future__ import annotations

import json

from sqlalchemy import inspect, select, text

from iris.dao import db
from iris.models import Document
from iris.schemas.backfills import PgvectorBackfillResult
from iris.schemas.enums import CrawlStatus, DocumentType
from iris.services.ingestion.embedding import loads_embedding


def setup_pgvector_embeddings(*, limit: int | None = None, create_index: bool = True) -> PgvectorBackfillResult:
    """Ensure pgvector schema exists and backfill from `documents.embedding` JSON strings.

    This intentionally keeps the existing string column as the compatibility/source column.
    `documents.embedding_vector` is a query-optimized mirror for Postgres semantic search.
    """
    session = db.current_session()
    _require_postgres()
    dimensions = _infer_dimensions()
    _ensure_pgvector_schema(dimensions=dimensions, create_index=create_index)

    statement = (
        select(Document)
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(Document.embedding.is_not(None))
        .where(text("embedding_vector is null"))
        .order_by(Document.id)
    )
    if limit:
        statement = statement.limit(limit)

    checked = 0
    updated = 0
    skipped = 0
    for document in session.execute(statement).scalars():
        checked += 1
        vector = loads_embedding(document.embedding)
        if len(vector) != dimensions:
            skipped += 1
            continue
        session.execute(
            text("update documents set embedding_vector = cast(:embedding as vector) where id = :document_id"),
            {"embedding": _vector_literal(vector), "document_id": document.id},
        )
        updated += 1
        if updated % 100 == 0:
            session.flush()
            print(f"pgvector backfill updated={updated} checked={checked}")

    return PgvectorBackfillResult(checked=checked, updated=updated, skipped=skipped, dimensions=dimensions)


def _require_postgres() -> None:
    session = db.current_session()
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise RuntimeError("pgvector setup requires a PostgreSQL database")


def _infer_dimensions() -> int:
    session = db.current_session()
    value = session.execute(
        select(Document.embedding)
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(Document.embedding.is_not(None))
        .limit(1)
    ).scalar_one_or_none()
    if not value:
        raise RuntimeError("cannot infer embedding dimensions: no embedded fetched essays")
    loaded = json.loads(value)
    return len(loaded)


def _ensure_pgvector_schema(*, dimensions: int, create_index: bool) -> None:
    session = db.current_session()
    connection = session.connection()
    session.execute(text("create extension if not exists vector"))
    columns = {column["name"] for column in inspect(connection).get_columns("documents")}
    if "embedding_vector" not in columns:
        session.execute(text(f"alter table documents add column embedding_vector vector({dimensions})"))
    session.execute(text("create index if not exists ix_documents_embedding_vector_present on documents(id) where embedding_vector is not null"))
    if create_index:
        session.execute(
            text(
                "create index if not exists ix_documents_embedding_vector_hnsw "
                "on documents using hnsw (embedding_vector vector_cosine_ops)"
            )
        )


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m iris.backfills.pgvector_embeddings")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--no-index", action="store_true")
    args = parser.parse_args()
    with db.session_scope():
        result = setup_pgvector_embeddings(limit=args.limit or None, create_index=not args.no_index)
        print(
            f"pgvector checked={result.checked} updated={result.updated} "
            f"skipped={result.skipped} dimensions={result.dimensions}"
        )


if __name__ == "__main__":
    main()
