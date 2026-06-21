"""Backfill crawl job index-run foreign keys."""

from __future__ import annotations

from sqlalchemy import text

from iris.dao import db


def migrate_index_run_fk() -> int:
    """Create and backfill the nullable `crawl_jobs.index_run_id` column."""
    session = db.current_session()
    session.execute(text("alter table crawl_jobs add column if not exists index_run_id integer"))
    session.execute(
        text(
            "do $$ begin "
            "if not exists (select 1 from pg_constraint where conname = 'fk_crawl_jobs_index_run_id') then "
            "alter table crawl_jobs add constraint fk_crawl_jobs_index_run_id "
            "foreign key (index_run_id) references index_runs(id); "
            "end if; end $$;"
        )
    )
    session.execute(text("create index if not exists ix_crawl_jobs_index_run_id on crawl_jobs(index_run_id)"))
    result = session.execute(
        text(
            "update crawl_jobs cj "
            "set index_run_id = ie.index_run_id "
            "from index_events ie "
            "where ie.crawl_job_id = cj.id "
            "and cj.index_run_id is null"
        )
    )
    return result.rowcount or 0


def main() -> int:
    with db.session_scope():
        print(f"backfilled={migrate_index_run_fk()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
