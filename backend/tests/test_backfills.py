from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from iris.backfills.document_crawl_job_fk import migrate_document_crawl_job_fk
from iris.backfills import metadata_embeddings
from iris.dao.documents import upsert_document
from iris.dao.sources import get_or_create_source
from iris.models import CrawlJob
from iris.schemas.ingestion import DocumentAnalysis


def test_metadata_backfill_respects_active_documents(monkeypatch):
    active = 0
    max_active = 0

    async def fake_analyze_document_async(**kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return DocumentAnalysis(
            title=kwargs["metadata_title"],
            summary="summary",
            topics=["topic"],
            category_slug="writing",
            document_type="essay",
        )

    monkeypatch.setattr(metadata_embeddings, "analyze_document_async", fake_analyze_document_async)
    items = [
        metadata_embeddings.BackfillDocumentInput(
            index=idx,
            total=5,
            document_id=idx,
            url=f"https://example.com/{idx}",
            title=f"Doc {idx}",
            document_type="essay",
            summary="old summary",
            topics=["old"],
            category_slug=None,
            extracted_text="body",
            author=None,
            has_published_date=False,
            link_count=0,
        )
        for idx in range(1, 6)
    ]

    outputs = asyncio.run(
        metadata_embeddings._run_document_workers(
            items,
            dry_run=True,
            openai_embeddings=True,
            max_attempts=1,
            active_documents=2,
        )
    )

    assert len(outputs) == 5
    assert max_active == 2
    assert not any(output.failed for output in outputs)


def test_document_crawl_job_backfill_sets_unambiguous_job(session):
    started = datetime(2026, 6, 12, tzinfo=timezone.utc)
    source = get_or_create_source("https://backfill-job.test", status="indexed")
    session.flush()
    job = CrawlJob(
        source_id=source.id,
        started_at=started,
        finished_at=started + timedelta(hours=1),
        status="succeeded",
        documents_indexed=1,
    )
    session.add(job)
    session.flush()
    document = upsert_document(
        source=source,
        url="https://backfill-job.test/post",
        document_type="essay",
        crawl_status="fetched",
        title="Post",
        author=None,
        published_at=None,
        extracted_text="post",
        summary="Post.",
        topics=["backfill"],
        embedding=None,
        content_hash="post",
    )
    document.last_crawled_at = started + timedelta(minutes=15)
    session.flush()

    assert migrate_document_crawl_job_fk() == 1
    assert document.crawl_job_id == job.id
