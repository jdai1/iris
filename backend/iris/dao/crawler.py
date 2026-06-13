"""Persistence helpers used by the crawler service."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from iris.dao import db
from iris.models import CrawlJob, Document, Source
from iris.schemas.enums import CrawlJobStatus, SourceStatus


def create_crawl_job(source: Source) -> CrawlJob:
    """Create a running crawl job for a source."""
    session = db.current_session()
    job = CrawlJob(source_id=source.id, status=CrawlJobStatus.RUNNING.value)
    session.add(job)
    session.flush()
    return job


def skip_crawl_job(job: CrawlJob, message: str) -> None:
    """Mark a crawl job skipped with a terminal message."""
    job.status = CrawlJobStatus.SKIPPED.value
    job.error = message
    job.finished_at = datetime.now(timezone.utc)
    db.current_session().flush()


def mark_source_crawling(source: Source) -> None:
    """Mark a source as currently crawling."""
    source.status = SourceStatus.CRAWLING.value
    source.last_checked_at = datetime.now(timezone.utc)
    db.current_session().flush()


def finish_crawl_job(job: CrawlJob) -> None:
    """Set the terminal timestamp on a crawl job."""
    job.finished_at = datetime.now(timezone.utc)
    db.current_session().flush()


def get_crawl_job(job_id: int) -> CrawlJob | None:
    """Fetch a crawl job by id."""
    return db.current_session().get(CrawlJob, job_id)


def get_source_by_domain(domain: str) -> Source | None:
    """Find a source row by canonical domain."""
    return db.current_session().execute(select(Source).where(Source.canonical_domain == domain)).scalar_one_or_none()


def get_document_by_url(url: str) -> Document | None:
    """Find a document by canonical URL."""
    return db.current_session().execute(select(Document).where(Document.url == url)).scalar_one_or_none()


def get_document_by_urls(urls: set[str]) -> Document | None:
    """Find the first document matching any URL in a set."""
    return db.current_session().execute(select(Document).where(Document.url.in_(urls))).scalar_one_or_none()


def set_document_link_targets(document: Document) -> None:
    """Resolve a document's outgoing links to known source/document rows."""
    for link in document.outgoing_links:
        target_document = get_document_by_url(link.target_url)
        if target_document:
            link.target_document_id = target_document.id
            link.target_source_id = target_document.source_id
            continue
        if link.target_domain:
            target_source = get_source_by_domain(link.target_domain)
            if target_source:
                link.target_source_id = target_source.id
    db.current_session().flush()
