"""Autopilot source selection, crawl orchestration, and post-crawl indexing."""

from __future__ import annotations

import logging
from dataclasses import asdict
from datetime import datetime, timezone

from iris.dao import db
from iris.dao import indexing as indexing_dao
from iris.dao.sources import get_or_create_source
from iris.services.ingestion.crawler import Crawler
from iris.models import CrawlJob, IndexRun, Source
from iris.schemas.enums import (
    CrawlJobStatus,
    IndexEventType,
    IndexMode,
    IndexRunStatus,
    SourceStatus,
)
from iris.schemas.indexing import SourcePriority, SourcePriorityPayload
from iris.services.common.url_utils import root_url_for_domain
from iris.services.ingestion.embedding import document_embedding_text, embed_text


logger = logging.getLogger("iris.indexer")

DOMAIN_SKIP_LIST = {
    "archive.org",
    "arxiv.org",
    "bbc.com",
    "businessinsider.com",
    "cnn.com",
    "cnbc.com",
    "dailymail.co.uk",
    "forbes.com",
    "google.com",
    "journals.plos.org",
    "link.springer.com",
    "nber.org",
    "npr.org",
    "open.spotify.com",
    "papers.ssrn.com",
    "pnas.org",
    "politico.com",
    "researchgate.net",
    "sites.google.com",
    "thelancet.com",
    "thedailybeast.com",
    "tvtropes.org",
    "wikipedia.org",
    "youtu.be",
    "youtube.com",
}


def autopilot(
    *,
    budget_sources: int,
    max_pages: int,
    max_depth: int,
    max_documents_per_source: int | None = None,
    skip_existing: bool = False,
    dry_run: bool = False,
    openai_embeddings: bool | None = None,
    seed_domain: str | None = None,
    active_pages: int = 4,
) -> IndexRun:
    """Run one bounded autopilot indexing pass over queued sources.

    The run plans a priority-ordered frontier once, then attempts each source in
    that plan until the budget is exhausted. Each source crawl is committed
    independently so progress survives later source-level failures.
    """
    with db.session_scope():
        run = IndexRun(
            status=IndexRunStatus.RUNNING.value,
            mode=IndexMode.AUTOPILOT.value,
            dry_run=1 if dry_run else 0,
            budget_sources=budget_sources,
            max_pages=max_pages,
            max_depth=max_depth,
        )
        try:
            indexing_dao.add_index_run(run)
            if seed_domain:
                normalized_seed_domain = seed_domain.strip().lower()
                seed_source = indexing_dao.get_source_by_domain(normalized_seed_domain)
                if seed_source is None:
                    seed_source = get_or_create_source(
                        f"https://{normalized_seed_domain}",
                        status=SourceStatus.QUEUED.value,
                    )
                    logger.info("seed source missing; bootstrapping domain=%s", normalized_seed_domain)
                if not dry_run:
                    _crawl_seed_source(
                        run,
                        seed_source,
                        seed_domain=normalized_seed_domain,
                        max_pages=max_pages,
                        max_depth=max_depth,
                        max_documents_per_source=max_documents_per_source,
                        skip_existing=skip_existing,
                        openai_embeddings=openai_embeddings,
                        active_pages=active_pages,
                    )
            planned = plan_sources(
                limit=budget_sources,
                seed_domain=seed_domain,
            )
            run.planned_sources = len(planned)
            logger.info(
                "index run %s planned %s source(s): %s",
                run.id,
                len(planned),
                ", ".join(item.source.canonical_domain for item in planned[:8])
                or "none",
            )
            indexing_dao.log_event(
                run,
                IndexEventType.PLAN_CREATED.value,
                f"planned {len(planned)} source(s)",
                payload={
                    "sources": [asdict(get_priority_payload(item)) for item in planned]
                },
            )
            db.commit()

            if dry_run:
                run.status = IndexRunStatus.SUCCEEDED.value
                run.stop_reason = "dry_run"
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return run

            for priority in planned:
                source = indexing_dao.get_source(priority.source.id)
                if not source or source.status != SourceStatus.QUEUED.value:
                    continue
                logger.info(
                    "source start domain=%s score=%.3f reason=%s",
                    source.canonical_domain,
                    priority.score,
                    priority.reason,
                )
                _run_one_source(
                    run,
                    source,
                    priority,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    max_documents_per_source=max_documents_per_source,
                    skip_existing=skip_existing,
                    openai_embeddings=openai_embeddings,
                    active_pages=active_pages,
                )
                db.commit()

            run.status = IndexRunStatus.SUCCEEDED.value
            run.stop_reason = "budget_exhausted" if planned else "no_queued_sources"
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return run
        except KeyboardInterrupt:
            run.status = IndexRunStatus.STOPPED.value
            run.stop_reason = "interrupted"
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            logger.info("index run %s stopped by user", run.id)
            raise
        except Exception as exc:
            run.status = IndexRunStatus.FAILED.value
            run.errors += 1
            run.stop_reason = str(exc)
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return run


def _run_one_source(
    run: IndexRun,
    source: Source,
    priority: SourcePriority,
    *,
    max_pages: int,
    max_depth: int,
    max_documents_per_source: int | None,
    skip_existing: bool,
    openai_embeddings: bool | None,
    active_pages: int,
) -> CrawlJob:
    """Crawl one planned source and fold the crawl result into its index run.

    This is the transaction boundary for source-level bookkeeping: it records
    start/finish events, normalizes the homepage URL, runs the crawler, updates
    aggregate counters, and embeds newly fetched documents when requested.
    """
    run.attempted_sources += 1
    root_url = root_url_for_domain(source.url)
    if source.url != root_url:
        indexing_dao.log_event(
            run,
            IndexEventType.SOURCE_HOMEPAGE_NORMALIZED.value,
            f"normalized homepage for {source.canonical_domain}",
            source_id=source.id,
            payload={"before": source.url, "after": root_url},
        )
        source.url = root_url
    before_docs = indexing_dao.count_documents_for_source(source)
    indexing_dao.log_event(
        run,
        IndexEventType.SOURCE_STARTED.value,
        f"starting {source.canonical_domain}",
        source_id=source.id,
        payload=asdict(get_priority_payload(priority)),
    )
    db.commit()
    job = Crawler().crawl_source(
        source,
        max_pages=max_pages,
        max_depth=max_depth,
        max_documents=max_documents_per_source,
        skip_existing=skip_existing,
        active_pages=active_pages,
    )
    job.index_run_id = run.id
    after_docs = indexing_dao.count_documents_for_source(source)
    new_docs = max(0, after_docs - before_docs)
    if job.status == CrawlJobStatus.SUCCEEDED.value:
        run.crawled_sources += 1
    elif (
        job.status == CrawlJobStatus.SKIPPED.value
        and source.status == SourceStatus.IGNORED.value
    ):
        run.ignored_sources += 1
    elif job.status == CrawlJobStatus.FAILED.value:
        run.errors += 1
    run.documents_indexed += job.documents_indexed
    run.links_seen += job.links_seen
    run.sources_discovered += job.sources_discovered

    embedded = 0
    if job.status == CrawlJobStatus.SUCCEEDED.value:
        embedded = embed_source_documents(source, openai=openai_embeddings)
    logger.info(
        "source finish domain=%s status=%s fetched=%s docs=%s links=%s discovered=%s embedded=%s",
        source.canonical_domain,
        job.status,
        job.pages_fetched,
        job.documents_indexed,
        job.links_seen,
        job.sources_discovered,
        embedded,
    )

    indexing_dao.log_event(
        run,
        IndexEventType.SOURCE_FINISHED.value,
        f"finished {source.canonical_domain}: {job.status}",
        source_id=source.id,
        crawl_job_id=job.id,
        payload={
            "status": job.status,
            "source_status": source.status,
            "new_documents": new_docs,
            "documents_indexed": job.documents_indexed,
            "pages_fetched": job.pages_fetched,
            "pages_failed": job.pages_failed,
            "max_documents_per_source": max_documents_per_source,
            "skip_existing": skip_existing,
            "links_seen": job.links_seen,
            "sources_discovered": job.sources_discovered,
            "embedded": embedded,
            "error": job.error,
        },
    )
    return job


def _crawl_seed_source(
    run: IndexRun,
    source: Source,
    *,
    seed_domain: str,
    max_pages: int,
    max_depth: int,
    max_documents_per_source: int | None,
    skip_existing: bool,
    openai_embeddings: bool | None,
    active_pages: int,
) -> CrawlJob:
    """Refresh an explicitly requested seed source before planning outward."""
    if source.status != SourceStatus.QUEUED.value:
        source.status = SourceStatus.QUEUED.value
    indexing_dao.log_event(
        run,
        IndexEventType.SOURCE_STARTED.value,
        f"refreshing seed {seed_domain}",
        source_id=source.id,
        payload={"seed_domain": seed_domain, "seed_refresh": True},
    )
    db.commit()
    before_docs = indexing_dao.count_documents_for_source(source)
    job = Crawler().crawl_source(
        source,
        max_pages=max_pages,
        max_depth=max_depth,
        max_documents=max_documents_per_source,
        skip_existing=skip_existing,
        active_pages=active_pages,
    )
    job.index_run_id = run.id
    after_docs = indexing_dao.count_documents_for_source(source)
    new_docs = max(0, after_docs - before_docs)
    embedded = 0
    if job.status == CrawlJobStatus.SUCCEEDED.value:
        embedded = embed_source_documents(source, openai=openai_embeddings)

    run.attempted_sources += 1
    if job.status == CrawlJobStatus.SUCCEEDED.value:
        run.crawled_sources += 1
    elif job.status == CrawlJobStatus.SKIPPED.value and source.status == SourceStatus.IGNORED.value:
        run.ignored_sources += 1
    elif job.status == CrawlJobStatus.FAILED.value:
        run.errors += 1
    run.documents_indexed += job.documents_indexed
    run.links_seen += job.links_seen
    run.sources_discovered += job.sources_discovered
    indexing_dao.log_event(
        run,
        IndexEventType.SOURCE_FINISHED.value,
        f"refreshed seed {seed_domain}: {job.status}",
        source_id=source.id,
        crawl_job_id=job.id,
        payload={
            "status": job.status,
            "source_status": source.status,
            "new_documents": new_docs,
            "documents_indexed": job.documents_indexed,
            "pages_fetched": job.pages_fetched,
            "pages_failed": job.pages_failed,
            "max_documents_per_source": max_documents_per_source,
            "skip_existing": skip_existing,
            "links_seen": job.links_seen,
            "sources_discovered": job.sources_discovered,
            "embedded": embedded,
            "error": job.error,
            "seed_domain": seed_domain,
            "seed_refresh": True,
        },
    )
    db.commit()
    return job


def plan_sources(
    limit: int = 20,
    *,
    seed_domain: str | None = None,
) -> list[SourcePriority]:
    """Rank queued sources by direct link proximity to an optional seed source.

    With a seed domain, only queued sources directly linked from that exact
    source domain's fetched essay documents are eligible. Without a seed, the
    frontier falls back to links from all indexed essay sources. Exact-domain
    platform blocks are filtered before the final score sort.
    """
    seed_source = None
    if seed_domain:
        normalized_seed_domain = seed_domain.strip().lower()
        seed_source = indexing_dao.get_source_by_domain(normalized_seed_domain)
        if not seed_source:
            raise ValueError(f"seed source domain not found: {normalized_seed_domain}")
    sources = indexing_dao.get_queued_sources_oldest_first()
    source_ids = [source.id for source in sources]
    inbound_by_source, referring_by_source = (
        indexing_dao.count_links_for_sources(source_ids) if source_ids else ({}, {})
    )
    bfs_links_by_source = (
        indexing_dao.count_bfs_links_for_sources(source_ids, seed_source.id)
        if seed_source
        else inbound_by_source
    )
    priorities = [
        _score_source_from_counts(
            source,
            inbound_links=inbound_by_source.get(source.id, 0),
            referring_sources=referring_by_source.get(source.id, 0),
            bfs_links=bfs_links_by_source.get(source.id, 0),
            bfs_seed_source_id=seed_source.id if seed_source else None,
            bfs_seed_domain=seed_source.canonical_domain if seed_source else None,
        )
        for source in sources
        if bfs_links_by_source.get(source.id, 0) > 0
        and source.canonical_domain not in DOMAIN_SKIP_LIST
    ]
    priorities.sort(key=lambda item: item.score, reverse=True)
    return priorities[:limit]


def embed_source_documents(source: Source, *, openai: bool | None = None) -> int:
    """Embed fetched essay documents for a source that do not yet have vectors."""
    documents = indexing_dao.get_source_documents_missing_embedding(source)
    for document in documents:
        text = document_embedding_text(
            title=document.title,
            summary=document.summary,
            topics=document.topics,
            extracted_text=document.extracted_text,
        )
        indexing_dao.set_document_embedding(document, embed_text(text, prefer_openai=openai))
    return len(documents)


def get_priority_payload(priority: SourcePriority) -> SourcePriorityPayload:
    """Convert a source priority object into a stable event/reporting payload."""
    return SourcePriorityPayload(
        source_id=priority.source.id,
        domain=priority.source.canonical_domain,
        status=priority.source.status,
        score=round(priority.score, 4),
        inbound_links=priority.inbound_links,
        referring_sources=priority.referring_sources,
        bfs_links=priority.bfs_links,
        bfs_seed_source_id=priority.bfs_seed_source_id,
        bfs_seed_domain=priority.bfs_seed_domain,
        reason=priority.reason,
    )


def _score_source_from_counts(
    source: Source,
    *,
    inbound_links: int,
    referring_sources: int,
    bfs_links: int,
    bfs_seed_source_id: int | None,
    bfs_seed_domain: str | None,
) -> SourcePriority:
    """Build a human-readable priority score from link-count signals."""
    score = float(bfs_links)
    reason_parts = [
        "algorithm=bfs",
        f"bfs_links={bfs_links}",
        f"inbound={inbound_links}",
        f"ref_sources={referring_sources}",
    ]
    if bfs_seed_domain:
        reason_parts.append(f"seed={bfs_seed_domain}")
    else:
        reason_parts.append("seed=all_indexed_sources")
    return SourcePriority(
        source=source,
        score=score,
        inbound_links=inbound_links,
        referring_sources=referring_sources,
        bfs_links=bfs_links,
        bfs_seed_source_id=bfs_seed_source_id,
        bfs_seed_domain=bfs_seed_domain,
        reason=", ".join(reason_parts),
    )
