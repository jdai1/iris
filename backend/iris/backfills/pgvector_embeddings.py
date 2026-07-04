"""Create and backfill the pgvector embedding column from legacy JSON rows."""

from __future__ import annotations

from sqlalchemy import inspect, text

from iris.dao import db
from iris.schemas.backfills import PgvectorBackfillResult
from iris.services.ingestion.embedding import loads_embedding

EMBEDDING_DIMENSIONS = 1536


def setup_pgvector_embeddings(*, limit: int | None = None, create_index: bool = True) -> PgvectorBackfillResult:
    """Ensure pgvector schema exists and backfill from legacy `documents.embedding` if present."""
    session = db.current_session()
    _require_postgres()
    dimensions = EMBEDDING_DIMENSIONS
    _ensure_pgvector_schema(dimensions=dimensions, create_index=create_index)
    columns = {column["name"] for column in inspect(session.connection()).get_columns("documents")}
    if "embedding" not in columns:
        return PgvectorBackfillResult(checked=0, updated=0, skipped=0, dimensions=dimensions)

    query = (
        "select id, embedding from documents "
        "where document_type = 'essay' and crawl_status = 'fetched' "
        "and embedding is not null and embedding_vector is null "
        "order by id"
    )
    if limit:
        query += " limit :limit"

    checked = 0
    updated = 0
    skipped = 0
    params = {"limit": limit} if limit else {}
    for row in session.execute(text(query), params):
        checked += 1
        vector = loads_embedding(row.embedding)
        if len(vector) != dimensions:
            skipped += 1
            continue
        session.execute(
            text("update documents set embedding_vector = cast(:embedding as vector) where id = :document_id"),
            {"embedding": _vector_literal(vector), "document_id": row.id},
        )
        updated += 1
        if updated % 100 == 0:
            session.flush()
            print(f"pgvector backfill updated={updated} checked={checked}")

    remaining = session.scalar(
        text(
            "select count(*) from documents where document_type = 'essay' and crawl_status = 'fetched' "
            "and embedding is not null and embedding_vector is null"
        )
    )
    if not remaining:
        session.execute(text("alter table documents drop column if exists embedding"))
    return PgvectorBackfillResult(checked=checked, updated=updated, skipped=skipped, dimensions=dimensions)


def _require_postgres() -> None:
    session = db.current_session()
    if session.bind is None or session.bind.dialect.name != "postgresql":
        raise RuntimeError("pgvector setup requires a PostgreSQL database")


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
