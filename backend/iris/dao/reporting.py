"""DAO helpers for status, audit, and index-run reporting queries."""

from __future__ import annotations

from sqlalchemy import func, select, text

from iris.dao import db
from iris.models import CrawlJob, Document, IndexEvent, IndexRun, Link, Source


def get_sql_rows(query: str):
    """Execute an ad hoc read query for the local SQL shell fallback."""
    return db.current_session().execute(text(query))


def count_sources_by_status() -> list[tuple[str, int]]:
    """Count sources by status."""
    session = db.current_session()
    return list(session.execute(select(Source.status, func.count(Source.id)).group_by(Source.status)))


def count_documents_by_type_status() -> list[tuple[str, str, int]]:
    """Count documents by type and crawl status."""
    session = db.current_session()
    return list(
        session.execute(
            select(Document.document_type, Document.crawl_status, func.count(Document.id)).group_by(
                Document.document_type, Document.crawl_status
            )
        )
    )


def count_links() -> int:
    """Count all discovered links."""
    return db.current_session().scalar(select(func.count(Link.id))) or 0


def count_resolved_links() -> int:
    """Count links resolved to a known document."""
    return db.current_session().scalar(select(func.count(Link.id)).where(Link.target_document_id.is_not(None))) or 0


def get_latest_crawl_jobs(limit: int = 5) -> list[CrawlJob]:
    """Return the latest crawl jobs for status output."""
    session = db.current_session()
    return session.execute(select(CrawlJob).order_by(CrawlJob.started_at.desc()).limit(limit)).scalars().all()


def count_documents_by_source_type() -> list[tuple[str, str, int]]:
    """Count documents by source domain and document type."""
    session = db.current_session()
    return list(
        session.execute(
            select(Source.canonical_domain, Document.document_type, func.count(Document.id))
            .join(Source, Document.source_id == Source.id)
            .group_by(Source.canonical_domain, Document.document_type)
            .order_by(Source.canonical_domain, Document.document_type)
        )
    )


def count_document_links(document_id: int) -> int:
    """Count outgoing links for one document."""
    session = db.current_session()
    return session.scalar(select(func.count(Link.id)).where(Link.source_document_id == document_id)) or 0


def get_index_events(run_id: int, *, limit: int | None = None) -> list[IndexEvent]:
    """Return events for one index run in chronological order."""
    session = db.current_session()
    statement = select(IndexEvent).where(IndexEvent.index_run_id == run_id).order_by(IndexEvent.created_at.asc())
    if limit:
        statement = statement.limit(limit)
    return session.execute(statement).scalars().all()


def get_latest_index_runs(limit: int) -> list[IndexRun]:
    """Return recent index runs."""
    session = db.current_session()
    return session.execute(select(IndexRun).order_by(IndexRun.started_at.desc()).limit(limit)).scalars().all()


def count_crawl_jobs_for_run(run_id: int) -> int:
    """Count crawl jobs attached to an index run."""
    session = db.current_session()
    return session.scalar(select(func.count(CrawlJob.id)).where(CrawlJob.index_run_id == run_id)) or 0


def get_index_run(run_id: int) -> IndexRun | None:
    """Fetch one index run by id."""
    return db.current_session().get(IndexRun, run_id)


def get_crawl_jobs_for_index_run(run_id: int) -> list[tuple[CrawlJob, Source]]:
    """Return crawl jobs and sources for an index run."""
    session = db.current_session()
    return (
        session.execute(
            select(CrawlJob, Source)
            .join(Source, CrawlJob.source_id == Source.id)
            .where(CrawlJob.index_run_id == run_id)
            .order_by(CrawlJob.started_at.asc())
        )
        .all()
    )

