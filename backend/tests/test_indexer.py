from __future__ import annotations

from iris.services.ingestion.embedding import dumps_embedding, embed_text
from iris.services.indexing import indexer
from iris.services.indexing.indexer import plan_sources, autopilot
from iris.models import CrawlJob, IndexEvent, IndexRun, Link
from iris.dao.sources import get_or_create_source
from iris.dao.documents import upsert_document


def add_essay(session, source, title: str, text: str):
    return upsert_document(
        source=source,
        url=f"https://{source.canonical_domain}/{title.lower().replace(' ', '-')}",
        document_type="essay",
        crawl_status="fetched",
        title=title,
        author=None,
        published_at=None,
        extracted_text=text,
        summary=text[:200],
        topics=["software", "essays"],
        embedding=dumps_embedding(embed_text(text)),
        content_hash=title,
    )


def test_source_priorities_prefer_referenced_sources(session):
    indexed = get_or_create_source("https://benkuhn.net", status="indexed")
    target = get_or_create_source("https://target.test", status="queued")
    doc = add_essay(session, indexed, "Essay", "substantive writing about software")
    session.add(
        Link(
            source_document_id=doc.id,
            target_url="https://target.test/",
            target_domain="target.test",
            target_source_id=target.id,
            link_type="external",
        )
    )
    session.flush()

    priorities = plan_sources(limit=2)

    assert priorities[0].source.id == target.id
    assert {item.source.id for item in priorities} == {target.id}


def test_source_priorities_use_bfs_seed_frontier(session):
    seed = get_or_create_source("https://seed.test", status="indexed")
    generic = get_or_create_source("https://indexed.test", status="indexed")
    liked_target = get_or_create_source("https://liked-target.test", status="queued")
    popular_target = get_or_create_source(
        "https://popular-target.test", status="queued"
    )
    seed_doc = add_essay(
        session, seed, "Seed Essay", "substantive writing about software"
    )
    generic_doc = add_essay(
        session, generic, "Generic Essay", "substantive writing about software"
    )
    session.add(
        Link(
            source_document_id=seed_doc.id,
            target_url="https://liked-target.test/",
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
                target_domain="popular-target.test",
                target_source_id=popular_target.id,
                link_type="external",
            )
        )
    session.flush()

    priorities = plan_sources(limit=2, seed_domain="seed.test")

    assert priorities[0].source.id == liked_target.id
    assert {item.source.id for item in priorities} == {liked_target.id}
    assert "algorithm=bfs" in priorities[0].reason
    assert "seed=seed.test" in priorities[0].reason
    assert "bfs_links=1" in priorities[0].reason


def test_source_priorities_skip_obvious_non_sources(session):
    seed = get_or_create_source("https://seed.test", status="indexed")
    youtube = get_or_create_source("https://youtube.com", status="queued")
    target = get_or_create_source("https://writer.test", status="queued")
    seed_doc = add_essay(
        session, seed, "Seed Essay", "substantive writing about software"
    )
    for idx in range(10):
        session.add(
            Link(
                source_document_id=seed_doc.id,
                target_url=f"https://youtube.com/watch?v={idx}",
                target_domain="youtube.com",
                target_source_id=youtube.id,
                link_type="external",
            )
        )
    session.add(
        Link(
            source_document_id=seed_doc.id,
            target_url="https://writer.test/",
            target_domain="writer.test",
            target_source_id=target.id,
            link_type="external",
        )
    )
    session.flush()

    priorities = plan_sources(limit=5, seed_domain="seed.test")

    assert [item.source.id for item in priorities] == [target.id]


def test_autopilot_dry_run_records_plan(session):
    ben = get_or_create_source("https://benkuhn.net", status="indexed")
    queued = get_or_create_source("https://queued.test", status="queued")
    doc = add_essay(session, ben, "Ben Essay", "substantive writing about software")
    session.add(
        Link(
            source_document_id=doc.id,
            target_url="https://queued.test/",
            target_domain="queued.test",
            target_source_id=queued.id,
            link_type="external",
        )
    )
    session.commit()

    run = autopilot(budget_sources=1, max_pages=3, max_depth=1, dry_run=True)

    stored_run = session.get(IndexRun, run.id)
    assert stored_run is not None
    assert stored_run.status == "succeeded"
    assert stored_run.dry_run == 1
    assert stored_run.planned_sources == 1
    events = session.query(IndexEvent).filter_by(index_run_id=run.id).all()
    assert [event.event_type for event in events] == ["plan_created"]


def test_autopilot_refreshes_existing_seed_before_planning(session, monkeypatch):
    seed = get_or_create_source("https://noahrousell.com", status="indexed")
    session.commit()
    crawled_domains = []

    class FakeCrawler:
        def crawl_source(self, source, **_kwargs):
            crawled_domains.append(source.canonical_domain)
            source.status = "indexed"
            job = CrawlJob(source_id=source.id, status="succeeded", pages_fetched=1)
            session.add(job)
            session.flush()
            return job

    monkeypatch.setattr(indexer, "Crawler", FakeCrawler)
    monkeypatch.setattr(indexer, "embed_source_documents", lambda *_args, **_kwargs: 0)

    run = autopilot(
        budget_sources=25,
        max_pages=2000,
        max_depth=2,
        max_documents_per_source=300,
        skip_existing=True,
        seed_domain="noahrousell.com",
        active_pages=2,
    )

    stored_seed = session.get(type(seed), seed.id)
    events = session.query(IndexEvent).filter_by(index_run_id=run.id).order_by(IndexEvent.id).all()

    assert crawled_domains == ["noahrousell.com"]
    assert stored_seed.status == "indexed"
    assert run.attempted_sources == 1
    assert run.crawled_sources == 1
    assert events[0].message == "refreshing seed noahrousell.com"
    assert events[1].message == "refreshed seed noahrousell.com: succeeded"
    assert events[2].event_type == "plan_created"


def test_crawl_job_can_link_to_index_run(session):
    run = IndexRun(status="running", mode="autopilot")
    source = get_or_create_source("https://queued.test", status="queued")
    session.add(run)
    session.flush()
    job = CrawlJob(source_id=source.id, index_run_id=run.id, status="succeeded")
    session.add(job)
    session.flush()

    stored = session.get(CrawlJob, job.id)

    assert stored.index_run_id == run.id
