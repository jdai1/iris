from __future__ import annotations

from iris.embedding import dumps_embedding, embed_text
from iris.indexer import plan_sources, run_autopilot
from iris.models import CrawlJob, IndexEvent, IndexRun, Link
from iris.repository import get_or_create_source, upsert_document


def add_essay(session, source, title: str, text: str):
    return upsert_document(
        session,
        source=source,
        url=f"https://{source.canonical_domain}/{title.lower().replace(' ', '-')}",
        final_url=f"https://{source.canonical_domain}/{title.lower().replace(' ', '-')}",
        document_type="essay",
        crawl_status="fetched",
        title=title,
        author=None,
        published_at=None,
        extracted_text=text,
        summary=text[:200],
        topics=["software", "essays"],
        embedding=dumps_embedding(embed_text(text)),
        quality_score=0.8,
        content_hash=title,
    )


def test_source_priorities_prefer_referenced_sources(session):
    indexed = get_or_create_source(session, "https://benkuhn.net", status="indexed")
    target = get_or_create_source(session, "https://target.test", status="queued")
    other = get_or_create_source(session, "https://other.test", status="queued")
    doc = add_essay(session, indexed, "Essay", "substantive writing about software")
    session.add(
        Link(
            source_document_id=doc.id,
            target_url="https://target.test/",
            normalized_target_url="https://target.test/",
            target_domain="target.test",
            target_source_id=target.id,
            link_type="external",
        )
    )
    session.flush()

    priorities = plan_sources(session, limit=2)

    assert priorities[0].source.id == target.id
    assert {item.source.id for item in priorities} == {target.id}


def test_source_priorities_prefer_liked_source_frontier(session):
    ben = get_or_create_source(session, "https://benkuhn.net", status="indexed")
    generic = get_or_create_source(session, "https://indexed.test", status="indexed")
    liked_target = get_or_create_source(session, "https://liked-target.test", status="queued")
    popular_target = get_or_create_source(session, "https://popular-target.test", status="queued")
    ben_doc = add_essay(session, ben, "Ben Essay", "substantive writing about software")
    generic_doc = add_essay(session, generic, "Generic Essay", "substantive writing about software")
    session.add(
        Link(
            source_document_id=ben_doc.id,
            target_url="https://liked-target.test/",
            normalized_target_url="https://liked-target.test/",
            target_domain="liked-target.test",
            target_source_id=liked_target.id,
            link_type="external",
        )
    )
    for idx in range(20):
        session.add(
            Link(
                source_document_id=generic_doc.id,
                target_url=f"https://popular-target.test/{idx}",
                normalized_target_url=f"https://popular-target.test/{idx}",
                target_domain="popular-target.test",
                target_source_id=popular_target.id,
                link_type="external",
            )
        )
    session.flush()

    priorities = plan_sources(session, limit=2)

    assert priorities[0].source.id == liked_target.id
    assert "seed=benkuhn.net" in priorities[0].reason
    assert "seed_links=1" in priorities[0].reason


def test_autopilot_dry_run_records_plan(session):
    ben = get_or_create_source(session, "https://benkuhn.net", status="indexed")
    queued = get_or_create_source(session, "https://queued.test", status="queued")
    doc = add_essay(session, ben, "Ben Essay", "substantive writing about software")
    session.add(
        Link(
            source_document_id=doc.id,
            target_url="https://queued.test/",
            normalized_target_url="https://queued.test/",
            target_domain="queued.test",
            target_source_id=queued.id,
            link_type="external",
        )
    )
    session.commit()

    run = run_autopilot(budget_sources=1, max_pages=3, max_depth=1, dry_run=True)

    stored_run = session.get(IndexRun, run.id)
    assert stored_run is not None
    assert stored_run.status == "succeeded"
    assert stored_run.dry_run == 1
    assert stored_run.planned_sources == 1
    events = session.query(IndexEvent).filter_by(index_run_id=run.id).all()
    assert [event.event_type for event in events] == ["plan_created"]


def test_crawl_job_can_link_to_index_run(session):
    run = IndexRun(status="running", mode="autopilot")
    source = get_or_create_source(session, "https://queued.test", status="queued")
    session.add(run)
    session.flush()
    job = CrawlJob(source_id=source.id, index_run_id=run.id, status="succeeded")
    session.add(job)
    session.flush()

    stored = session.get(CrawlJob, job.id)

    assert stored.index_run_id == run.id
