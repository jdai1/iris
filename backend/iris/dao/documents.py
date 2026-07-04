"""Persistence helpers for document rows."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from iris.dao import db
from iris.models import Document, Source
from iris.schemas.ingestion import DocumentAnalysis
from iris.services.common.url_utils import normalize_url
from iris.services.ingestion.embedding import coerce_embedding_vector, dumps_embedding


def upsert_document(
    *,
    source: Source,
    crawl_job_id: int | None = None,
    url: str,
    document_type: str,
    crawl_status: str,
    title: str | None,
    author: str | None,
    published_at,
    extracted_text: str | None,
    summary: str | None,
    topics: list[str],
    embedding: list[float] | str | None,
    content_hash: str | None,
) -> Document:
    """Insert or update a document row by canonical URL."""
    session = db.current_session()
    url = normalize_url(url)
    document = session.execute(select(Document).where(Document.url == url)).scalar_one_or_none()
    if document is None:
        document = Document(
            source_id=source.id,
            url=url,
        )
        session.add(document)
    document.source_id = source.id
    document.crawl_job_id = crawl_job_id
    document.document_type = document_type
    document.crawl_status = crawl_status
    document.title = title
    document.author = author
    document.published_at = published_at
    document.extracted_text = extracted_text
    document.summary = summary
    document.topics = [topic for topic in topics if topic]
    document.embedding_vector = _store_embedding_vector(coerce_embedding_vector(embedding))
    document.content_hash = content_hash
    document.last_crawled_at = datetime.now(timezone.utc)
    session.flush()
    return document


def update_document_analysis(document: Document, analysis: DocumentAnalysis) -> None:
    """Persist refreshed LLM analysis fields for an existing document."""
    document.document_type = analysis.document_type
    document.title = analysis.title
    document.summary = analysis.summary
    document.topics = [topic for topic in analysis.topics if topic]
    db.current_session().flush()


def update_document_embedding(document: Document, embedding: list[float] | str | None) -> None:
    """Persist a refreshed embedding for an existing document."""
    document.embedding_vector = _store_embedding_vector(coerce_embedding_vector(embedding))
    db.current_session().flush()


def _store_embedding_vector(vector: list[float] | None):
    session = db.current_session()
    if vector is None:
        return None
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        return dumps_embedding(vector)
    return vector
