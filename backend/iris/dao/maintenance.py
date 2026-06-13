"""DAO helpers for manual source and document maintenance tasks."""

from __future__ import annotations

from urllib.parse import urlparse

from sqlalchemy import delete, select, update

from iris.dao import db
from iris.models import Document, Link, Source
from iris.schemas.enums import CrawlStatus, DocumentType, SourceStatus


BOILERPLATE_SUMMARY_MARKERS = (
    "Home About",
    "RSS Feed",
    "Blogroll",
    "Facebook Twitter",
    "LinkedIn Print",
    "This post is more than",
    "Comments Feed",
    "Skip to content",
    "Toggle navigation",
    "Privacy Policy",
    "Share this",
    "Subscribe",
)

WEAK_TOPIC_MARKERS = {
    "home",
    "about",
    "blog",
    "post",
    "posts",
    "comment",
    "comments",
    "says",
    "feed",
    "rss",
    "facebook",
    "twitter",
    "linkedin",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "good",
    "like",
    "just",
    "will",
    "well",
    "thing",
    "things",
    "time",
    "people",
    "some",
    "them",
    "they",
    "than",
    "more",
    "much",
    "only",
}


def get_queued_sources(limit: int | None = None) -> list[Source]:
    """Return queued sources in insertion order for manual classification."""
    session = db.current_session()
    statement = select(Source).where(Source.status == SourceStatus.QUEUED.value).order_by(Source.first_seen_at.asc())
    if limit:
        statement = statement.limit(limit)
    return session.execute(statement).scalars().all()


def set_source_ignored(domain_or_url: str, *, reason: str, delete_rows: bool) -> tuple[Source | None, int]:
    """Mark a source ignored and optionally delete its indexed documents."""
    session = db.current_session()
    domain = domain_or_url
    if "://" in domain:
        domain = urlparse(domain).netloc
    domain = domain.lower().removeprefix("www.")
    source = session.execute(select(Source).where(Source.canonical_domain == domain)).scalar_one_or_none()
    if not source:
        return None, 0
    document_ids = list(session.scalars(select(Document.id).where(Document.source_id == source.id)))
    if delete_rows and document_ids:
        session.execute(delete(Link).where(Link.source_document_id.in_(document_ids)))
        session.execute(delete(Link).where(Link.target_document_id.in_(document_ids)))
        session.execute(delete(Document).where(Document.id.in_(document_ids)))
    session.execute(update(Link).where(Link.target_source_id == source.id).values(target_source_id=None))
    source.status = SourceStatus.IGNORED.value
    source.description = reason
    return source, len(document_ids) if delete_rows else 0


def get_documents_for_embedding(*, missing_only: bool, limit: int | None) -> list[Document]:
    """Return essay documents selected for manual embedding backfill."""
    session = db.current_session()
    statement = (
        select(Document)
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .order_by(Document.last_crawled_at.desc())
    )
    if missing_only:
        statement = statement.where(Document.embedding.is_(None))
    if limit:
        statement = statement.limit(limit)
    return session.execute(statement).scalars().all()


def get_fetched_documents(*, source_domain: str | None, limit: int | None) -> list[Document]:
    """Return fetched documents for audit or reclassification commands."""
    session = db.current_session()
    statement = (
        select(Document)
        .join(Source, Document.source_id == Source.id)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .order_by(Document.last_crawled_at.desc())
    )
    if source_domain:
        statement = statement.where(Source.canonical_domain == source_domain)
    if limit:
        statement = statement.limit(limit)
    return session.execute(statement).scalars().all()


def get_documents_for_metadata_backfill(
    *,
    source_domain: str | None,
    limit: int | None,
    suspicious_only: bool,
) -> list[Document]:
    """Return fetched essays that should have LLM metadata refreshed."""
    session = db.current_session()
    statement = (
        select(Document)
        .join(Source, Document.source_id == Source.id)
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .order_by(Document.id.asc())
    )
    if source_domain:
        statement = statement.where(Source.canonical_domain == source_domain)
    documents = session.execute(statement).scalars().all()
    if suspicious_only:
        documents = [document for document in documents if is_suspicious_metadata(document)]
    if limit:
        documents = documents[:limit]
    return documents


def is_suspicious_metadata(document: Document) -> bool:
    """Return whether document summary/topics look like boilerplate or weak keywords."""
    summary = (document.summary or "").strip()
    if not summary or len(summary) < 45:
        return True
    summary_lower = summary.lower()
    if any(marker.lower() in summary_lower for marker in BOILERPLATE_SUMMARY_MARKERS):
        return True
    topics = [str(topic).lower().strip() for topic in document.topics or [] if str(topic).strip()]
    if not topics:
        return True
    weak_count = sum(1 for topic in topics if topic in WEAK_TOPIC_MARKERS or len(topic) <= 3)
    return weak_count >= max(3, len(topics) // 2)
