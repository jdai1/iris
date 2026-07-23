from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from iris.backfills.document_crawl_job_fk import migrate_document_crawl_job_fk
from iris.backfills import document_summaries, metadata_embeddings
from iris.dao.documents import upsert_document
from iris.dao.sources import get_or_create_source
from iris.models import CrawlJob
from iris.schemas.ingestion import DocumentAnalysis
from iris.services.retrieval import source_profiles


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
            one_liner=None,
            audience=None,
            takeaways=[],
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
            embed=False,
            openai_embeddings=True,
            max_attempts=1,
            active_documents=2,
        )
    )

    assert len(outputs) == 5
    assert max_active == 2
    assert not any(output.failed for output in outputs)


def test_summary_backfill_respects_active_documents(monkeypatch):
    active = 0
    max_active = 0

    async def fake_analyze_document_async(**kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return DocumentAnalysis(
            title="new title",
            summary=f"summary for {kwargs['metadata_title']}",
            topics=["new"],
            category_slug="writing",
            document_type="collection",
        )

    monkeypatch.setattr(document_summaries, "analyze_document_async", fake_analyze_document_async)
    items = [
        document_summaries.SummaryBackfillItem(
            index=idx,
            total=5,
            document_id=idx,
            url=f"https://example.com/{idx}",
            title=f"Doc {idx}",
            summary="old summary",
            one_liner=None,
            audience=None,
            takeaways=[],
            extracted_text="body",
            author=None,
            has_published_date=False,
            link_count=0,
        )
        for idx in range(1, 6)
    ]

    outputs = asyncio.run(
        document_summaries._run_summary_workers(
            items,
            max_attempts=1,
            active_documents=2,
        )
    )

    assert len(outputs) == 5
    assert max_active == 2
    assert not any(output.failed for output in outputs)


def test_source_profile_normalization_filters_controlled_lists():
    payload = {
        "audiences": ["Software engineers", "made up audience", "Software engineers", "Mathematics readers", "General curious readers", "Writers and bloggers"],
        "themes": ["Mathematics", "tiny bespoke label", "AI and machine learning", "Rationality", "Social theory", "Writing and communication", "Software engineering"],
        "writing_style": ["Technical", "long bespoke style label", "Analytical", "Technical", "Dense", "Conversational", "Playful"],
        "opinions": [{"opinion": "Bloggers reveal their real worldview through recurring claims."}, {"take": "Legacy take shape is still accepted."}],
    }

    normalized = source_profiles.normalize_profile_payload(
        payload,
        source_profiles.ProfileInput(
            source_id=1,
            domain="example.com",
            url="https://example.com",
            fingerprint="test",
            scraped_facts={},
            documents=[],
        ),
    )

    assert normalized["audiences"] == ["Software engineers", "Mathematics readers", "General curious readers", "Writers and bloggers"]
    assert normalized["themes"] == [
        "Mathematics",
        "AI and machine learning",
        "Rationality",
        "Social theory",
        "Writing and communication",
        "Software engineering",
    ]
    assert normalized["writing_style"] == ["Technical", "Analytical", "Dense", "Conversational"]
    assert normalized["opinions"] == [
        {"take": "Bloggers reveal their real worldview through recurring claims."},
        {"take": "Legacy take shape is still accepted."},
    ]


def test_summary_backfill_updates_only_summary(session, monkeypatch):
    source = get_or_create_source("https://summary-backfill.test", status="indexed")
    document = upsert_document(
        source=source,
        url="https://summary-backfill.test/post",
        document_type="essay",
        crawl_status="fetched",
        title="Original title",
        author=None,
        published_at=None,
        extracted_text="post body",
        summary="Old summary.",
        topics=["old-topic"],
        embedding=None,
        content_hash="post",
    )

    async def fake_analyze_document_async(**_kwargs):
        return DocumentAnalysis(
            title="Changed title",
            summary="New objective summary.",
            one_liner="Core idea.",
            audience="Primary audience.",
            takeaways=["One", "Two"],
            topics=["new-topic"],
            category_slug="software",
            document_type="reference",
        )

    monkeypatch.setattr(document_summaries, "analyze_document_async", fake_analyze_document_async)

    result = document_summaries.backfill_document_summaries(
        source_domain="summary-backfill.test",
        limit=0,
        dry_run=False,
        max_attempts=1,
        active_documents=1,
    )

    session.refresh(document)
    assert result.checked == 1
    assert result.changed == 1
    assert result.failed == 0
    assert document.summary == "New objective summary."
    assert document.one_liner == "Core idea."
    assert document.audience == "Primary audience."
    assert document.takeaways == ["One", "Two"]
    assert document.title == "Original title"
    assert document.document_type == "essay"
    assert document.topics == ["old-topic"]


def test_alembic_upgrade_head_creates_schema(tmp_path):
    db_path = tmp_path / "alembic.db"
    env = {
        **os.environ,
        "DEV_DATABASE_URL": f"sqlite:///{db_path}",
        "PYTHONPATH": "backend",
    }

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


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
