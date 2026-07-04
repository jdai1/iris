"""Persistence and graph-count helpers used by indexing services."""

from __future__ import annotations

import json
from collections.abc import Mapping

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import aliased

from iris.dao import db
from iris.models import Document, IndexEvent, IndexRun, Link, Source
from iris.schemas.enums import CrawlStatus, DocumentType, SourceStatus


def add_index_run(run: IndexRun) -> None:
    """Persist a new index run."""
    session = db.current_session()
    session.add(run)
    session.flush()


def get_source(source_id: int) -> Source | None:
    """Fetch a source by id."""
    return db.current_session().get(Source, source_id)


def count_documents_for_source(source: Source) -> int:
    """Count documents currently attached to a source."""
    session = db.current_session()
    return session.scalar(select(func.count(Document.id)).where(Document.source_id == source.id)) or 0


def log_event(
    run: IndexRun,
    event_type: str,
    message: str,
    *,
    source_id: int | None = None,
    crawl_job_id: int | None = None,
    payload: Mapping[str, object] | None = None,
) -> IndexEvent:
    """Persist an index event with an optional JSON payload."""
    session = db.current_session()
    event = IndexEvent(
        index_run_id=run.id,
        source_id=source_id,
        crawl_job_id=crawl_job_id,
        event_type=event_type,
        message=message,
        payload=json.dumps(payload, sort_keys=True) if payload else None,
    )
    session.add(event)
    session.flush()
    return event


def get_queued_sources_oldest_first() -> list[Source]:
    """Return queued sources in discovery order."""
    session = db.current_session()
    return (
        session.execute(select(Source).where(Source.status == SourceStatus.QUEUED.value).order_by(Source.first_seen_at.asc()))
        .scalars()
        .all()
    )


def get_source_by_domain(domain: str) -> Source | None:
    """Fetch a source by canonical domain."""
    return db.current_session().execute(select(Source).where(Source.canonical_domain == domain)).scalar_one_or_none()


def count_links_for_sources(source_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    """Count inbound links and referring source counts for candidate sources."""
    if not source_ids:
        return {}, {}
    session = db.current_session()
    referring_source = aliased(Source)
    rows = session.execute(
        select(
            Link.target_source_id,
            func.count(Link.id),
            func.count(distinct(Document.source_id)),
        )
        .join(Document, Link.source_document_id == Document.id)
        .join(referring_source, Document.source_id == referring_source.id)
        .where(Link.target_source_id.in_(source_ids))
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(referring_source.status == SourceStatus.INDEXED.value)
        .group_by(Link.target_source_id)
    ).all()
    inbound_by_source: dict[int, int] = {}
    referring_by_source: dict[int, int] = {}
    for source_id, inbound_links, referring_sources in rows:
        if source_id is None:
            continue
        inbound_by_source[int(source_id)] = int(inbound_links or 0)
        referring_by_source[int(source_id)] = int(referring_sources or 0)
    return inbound_by_source, referring_by_source


def count_bfs_links_for_sources(source_ids: list[int], seed_source_id: int) -> dict[int, int]:
    """Count candidate links originating from a BFS seed source."""
    if not source_ids:
        return {}
    session = db.current_session()
    rows = session.execute(
        select(
            Link.target_source_id,
            func.count(Link.id),
        )
        .join(Document, Link.source_document_id == Document.id)
        .where(Link.target_source_id.in_(source_ids))
        .where(Document.source_id == seed_source_id)
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .group_by(Link.target_source_id)
    ).all()
    bfs_links_by_source: dict[int, int] = {}
    for source_id, bfs_links in rows:
        if source_id is None:
            continue
        bfs_links_by_source[int(source_id)] = int(bfs_links or 0)
    return bfs_links_by_source


def get_source_documents_missing_embedding(source: Source) -> list[Document]:
    """Return fetched essay documents for a source that lack embeddings."""
    session = db.current_session()
    return (
        session.execute(
            select(Document)
            .where(Document.source_id == source.id)
            .where(Document.document_type == DocumentType.ESSAY.value)
            .where(Document.crawl_status == CrawlStatus.FETCHED.value)
            .where(Document.embedding_vector.is_(None))
        )
        .scalars()
        .all()
    )


def set_document_embedding(document: Document, embedding: list[float] | str) -> None:
    """Store an embedding vector on a document."""
    from iris.dao.documents import _store_embedding_vector
    from iris.services.ingestion.embedding import coerce_embedding_vector

    document.embedding_vector = _store_embedding_vector(coerce_embedding_vector(embedding))
    db.current_session().flush()
