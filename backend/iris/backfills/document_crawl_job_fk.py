"""Backfill document crawl-job provenance."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import inspect, select, text

from iris.dao import db
from iris.models import CrawlJob, Document


def migrate_document_crawl_job_fk() -> int:
    """Create and backfill the nullable `documents.crawl_job_id` column."""
    session = db.current_session()
    session.flush()
    _ensure_column()
    session.flush()
    jobs_by_source: dict[int, list[CrawlJob]] = {}
    jobs = session.execute(select(CrawlJob).order_by(CrawlJob.started_at)).scalars().all()
    for job in jobs:
        jobs_by_source.setdefault(job.source_id, []).append(job)

    changed = 0
    documents = session.execute(select(Document).where(Document.crawl_job_id.is_(None))).scalars().all()
    for document in documents:
        if not document.last_crawled_at:
            continue
        crawled_at = _comparison_time(document.last_crawled_at)
        matches = [
            job
            for job in jobs_by_source.get(document.source_id, [])
            if _comparison_time(job.started_at)
            <= crawled_at
            <= _comparison_time(job.finished_at or datetime.now(timezone.utc))
        ]
        if len(matches) != 1:
            continue
        document.crawl_job_id = matches[0].id
        changed += 1
    return changed


def _ensure_column() -> None:
    session = db.current_session()
    connection = session.connection()
    columns = {column["name"] for column in inspect(connection).get_columns("documents")}
    if "crawl_job_id" not in columns:
        session.execute(text("alter table documents add column crawl_job_id integer"))
    session.execute(text("create index if not exists ix_documents_crawl_job_id on documents(crawl_job_id)"))
    if connection.dialect.name == "postgresql":
        session.execute(
            text(
                "do $$ begin "
                "if not exists (select 1 from pg_constraint where conname = 'fk_documents_crawl_job_id') then "
                "alter table documents add constraint fk_documents_crawl_job_id "
                "foreign key (crawl_job_id) references crawl_jobs(id); "
                "end if; end $$;"
            )
        )


def _comparison_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def main() -> int:
    with db.session_scope():
        print(f"backfilled={migrate_document_crawl_job_fk()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
