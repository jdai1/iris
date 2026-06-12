from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, aliased

from iris.dao.db import SessionLocal, init_db
from iris.models import (
    CrawlJob,
    CrawlJobStatus,
    CrawlStatus,
    Document,
    DocumentType,
    IndexEvent,
    IndexEventType,
    IndexMode,
    IndexRun,
    IndexRunStatus,
    Link,
    Source,
    SourceStatus,
)
from iris.services.common.url_utils import root_url_for_domain
from iris.services.ingestion.crawler import Crawler
from iris.services.ingestion.embedding import dumps_embedding, embed_text


logger = logging.getLogger("iris.indexer")

OBVIOUS_NON_SOURCE_DOMAIN_PARTS = {
    "archive.org",
    "arxiv.org",
    "bbc.com",
    "businessinsider.com",
    "cnn.com",
    "cnbc.com",
    "dailymail.co.uk",
    "forbes.com",
    "google.",
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
    "youtu.be",
    "youtube.com",
}

SPIDER_SEED_DOMAIN = "benkuhn.net"


@dataclass(frozen=True)
class SourcePriority:
    source: Source
    score: float
    inbound_links: int
    referring_sources: int
    feed_signal: float
    manual_seed_bonus: float
    reason: str


def log_event(
    session: Session,
    run: IndexRun,
    event_type: str,
    message: str,
    *,
    source_id: int | None = None,
    crawl_job_id: int | None = None,
    payload: dict | None = None,
) -> IndexEvent:
    event = IndexEvent(
        index_run_id=run.id,
        source_id=source_id,
        crawl_job_id=crawl_job_id,
        event_type=event_type,
        message=message,
        payload=json.dumps(payload, sort_keys=True) if payload else None,
    )
    session.add(event)
    session.flush()
    return event


def plan_sources(session: Session, limit: int = 20) -> list[SourcePriority]:
    sources = session.execute(
        select(Source)
        .where(Source.status == SourceStatus.QUEUED.value)
        .order_by(Source.first_seen_at.asc())
    ).scalars().all()
    source_ids = [source.id for source in sources]
    inbound_by_source, referring_by_source = _link_counts_for_sources(session, source_ids)
    seed_links_by_source = _seed_link_counts_for_sources(session, source_ids)
    priorities = [
        _score_source_from_counts(
            source,
            inbound_links=inbound_by_source.get(source.id, 0),
            referring_sources=referring_by_source.get(source.id, 0),
            seed_links=seed_links_by_source.get(source.id, 0),
        )
        for source in sources
        if seed_links_by_source.get(source.id, 0) > 0
    ]
    priorities.sort(key=lambda item: item.score, reverse=True)
    return priorities[:limit]


def _score_source(session: Session, source: Source) -> SourcePriority:
    inbound_links = session.scalar(
        select(func.count(Link.id))
        .join(Document, Link.source_document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .where(Link.target_source_id == source.id)
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(Source.status == SourceStatus.INDEXED.value)
    ) or 0
    referring_sources = session.scalar(
        select(func.count(distinct(Document.source_id)))
        .join(Link, Link.source_document_id == Document.id)
        .join(Source, Document.source_id == Source.id)
        .where(Link.target_source_id == source.id)
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(Source.status == SourceStatus.INDEXED.value)
    ) or 0
    seed_links_by_source = _seed_link_counts_for_sources(session, [source.id])
    return _score_source_from_counts(
        source,
        inbound_links=inbound_links,
        referring_sources=referring_sources,
        seed_links=seed_links_by_source.get(source.id, 0),
    )


def _link_counts_for_sources(session: Session, source_ids: list[int]) -> tuple[dict[int, int], dict[int, int]]:
    if not source_ids:
        return {}, {}
    referring_source = aliased(Source)
    rows = session.execute(
        select(
            Link.target_source_id,
            func.count(Link.id),
            func.count(distinct(Document.source_id)),
        )
        .join(Document, Link.source_document_id == Document.id)
        .join(referring_source, Document.source_id == referring_source.id)
        .where(Link.target_source_id.in_(source_ids))
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(referring_source.status == SourceStatus.INDEXED.value)
        .group_by(Link.target_source_id)
    ).all()
    inbound_by_source: dict[int, int] = {}
    referring_by_source: dict[int, int] = {}
    for source_id, inbound_links, referring_sources in rows:
        if source_id is None:
            continue
        inbound_by_source[int(source_id)] = int(inbound_links or 0)
        referring_by_source[int(source_id)] = int(referring_sources or 0)
    return inbound_by_source, referring_by_source


def _seed_link_counts_for_sources(session: Session, source_ids: list[int]) -> dict[int, int]:
    if not source_ids:
        return {}
    referring_source = aliased(Source)
    rows = session.execute(
        select(
            Link.target_source_id,
            func.count(Link.id),
        )
        .join(Document, Link.source_document_id == Document.id)
        .join(referring_source, Document.source_id == referring_source.id)
        .where(Link.target_source_id.in_(source_ids))
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(referring_source.canonical_domain == SPIDER_SEED_DOMAIN)
        .group_by(Link.target_source_id)
    ).all()
    seed_links_by_source: dict[int, int] = {}
    for source_id, seed_links in rows:
        if source_id is None:
            continue
        seed_links_by_source[int(source_id)] = int(seed_links or 0)
    return seed_links_by_source


def _score_source_from_counts(
    source: Source,
    *,
    inbound_links: int,
    referring_sources: int,
    seed_links: int = 0,
) -> SourcePriority:
    feed_signal = 1.0 if source.rss_url or source.sitemap_url else 0.0
    manual_seed_bonus = 1.0 if source.discovered_from_source_id is None else 0.0
    skip_penalty = 1.0 if _has_obvious_non_source_domain(source.canonical_domain) else 0.0
    score = (
        100.0 * seed_links
        + 2.0 * feed_signal
        - 500.0 * skip_penalty
    )
    reason_parts = [
        f"seed={SPIDER_SEED_DOMAIN}",
        f"seed_links={seed_links}",
        f"inbound={inbound_links}",
        f"ref_sources={referring_sources}",
    ]
    if feed_signal:
        reason_parts.append("feed/sitemap")
    if manual_seed_bonus:
        reason_parts.append("manual_seed")
    if skip_penalty:
        reason_parts.append("obvious_non_source")
    return SourcePriority(
        source=source,
        score=score,
        inbound_links=inbound_links,
        referring_sources=referring_sources,
        feed_signal=feed_signal,
        manual_seed_bonus=manual_seed_bonus,
        reason=", ".join(reason_parts),
    )


def _has_obvious_non_source_domain(domain: str | None) -> bool:
    normalized = (domain or "").lower()
    return any(part in normalized for part in OBVIOUS_NON_SOURCE_DOMAIN_PARTS)


def run_autopilot(
    *,
    budget_sources: int,
    max_pages: int,
    max_depth: int,
    max_documents_per_source: int | None = None,
    skip_existing: bool = False,
    dry_run: bool = False,
    embed: bool = True,
    openai_embeddings: bool | None = None,
) -> IndexRun:
    init_db()
    session = SessionLocal()
    run = IndexRun(
        status=IndexRunStatus.RUNNING.value,
        mode=IndexMode.AUTOPILOT.value,
        dry_run=1 if dry_run else 0,
        budget_sources=budget_sources,
        max_pages=max_pages,
        max_depth=max_depth,
    )
    try:
        session.add(run)
        session.flush()
        planned = plan_sources(session, limit=budget_sources)
        run.planned_sources = len(planned)
        logger.info(
            "index run %s planned %s source(s): %s",
            run.id,
            len(planned),
            ", ".join(item.source.canonical_domain for item in planned[:8]) or "none",
        )
        log_event(
            session,
            run,
            IndexEventType.PLAN_CREATED.value,
            f"planned {len(planned)} source(s)",
            payload={"sources": [_priority_payload(item) for item in planned]},
        )
        session.commit()

        if dry_run:
            run.status = IndexRunStatus.SUCCEEDED.value
            run.stop_reason = "dry_run"
            run.finished_at = datetime.now(timezone.utc)
            session.commit()
            return run

        for priority in planned:
            source = session.get(Source, priority.source.id)
            if not source or source.status != SourceStatus.QUEUED.value:
                continue
            logger.info(
                "source start domain=%s score=%.3f reason=%s",
                source.canonical_domain,
                priority.score,
                priority.reason,
            )
            _run_one_source(
                session,
                run,
                source,
                priority,
                max_pages=max_pages,
                max_depth=max_depth,
                max_documents_per_source=max_documents_per_source,
                skip_existing=skip_existing,
                embed=embed,
                openai_embeddings=openai_embeddings,
            )
            session.commit()

        run.status = IndexRunStatus.SUCCEEDED.value
        run.stop_reason = "budget_exhausted" if planned else "no_queued_sources"
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        return run
    except KeyboardInterrupt:
        run.status = IndexRunStatus.STOPPED.value
        run.stop_reason = "interrupted"
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        logger.info("index run %s stopped by user", run.id)
        raise
    except Exception as exc:
        session.rollback()
        session = SessionLocal()
        existing = session.get(IndexRun, run.id)
        if existing:
            existing.status = IndexRunStatus.FAILED.value
            existing.errors += 1
            existing.stop_reason = str(exc)
            existing.finished_at = datetime.now(timezone.utc)
            session.commit()
            return existing
        raise
    finally:
        session.close()


def _run_one_source(
    session: Session,
    run: IndexRun,
    source: Source,
    priority: SourcePriority,
    *,
    max_pages: int,
    max_depth: int,
    max_documents_per_source: int | None,
    skip_existing: bool,
    embed: bool,
    openai_embeddings: bool | None,
) -> CrawlJob:
    run.attempted_sources += 1
    root_url = root_url_for_domain(source.url)
    if source.url != root_url:
        log_event(
            session,
            run,
            IndexEventType.SOURCE_HOMEPAGE_NORMALIZED.value,
            f"normalized homepage for {source.canonical_domain}",
            source_id=source.id,
            payload={"before": source.url, "after": root_url},
        )
        source.url = root_url
    before_docs = session.scalar(select(func.count(Document.id)).where(Document.source_id == source.id)) or 0
    log_event(
        session,
        run,
        IndexEventType.SOURCE_STARTED.value,
        f"starting {source.canonical_domain}",
        source_id=source.id,
        payload=_priority_payload(priority),
    )
    session.commit()
    job = Crawler(session).crawl_source(
        source,
        max_pages=max_pages,
        max_depth=max_depth,
        max_documents=max_documents_per_source,
        skip_existing=skip_existing,
    )
    job.index_run_id = run.id
    after_docs = session.scalar(select(func.count(Document.id)).where(Document.source_id == source.id)) or 0
    new_docs = max(0, after_docs - before_docs)
    if job.status == CrawlJobStatus.SUCCEEDED.value:
        run.crawled_sources += 1
    elif job.status == CrawlJobStatus.SKIPPED.value and source.status == SourceStatus.IGNORED.value:
        run.ignored_sources += 1
    elif job.status == CrawlJobStatus.FAILED.value:
        run.errors += 1
    run.documents_indexed += job.documents_indexed
    run.links_seen += job.links_seen
    run.sources_discovered += job.sources_discovered

    embedded = 0
    if embed and job.status == CrawlJobStatus.SUCCEEDED.value:
        embedded = embed_source_documents(session, source, openai=openai_embeddings)
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

    log_event(
        session,
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


def embed_source_documents(session: Session, source: Source, *, openai: bool | None = None) -> int:
    documents = session.execute(
        select(Document)
        .where(Document.source_id == source.id)
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(Document.embedding.is_(None))
    ).scalars().all()
    for document in documents:
        text = f"{document.title or ''}\n{document.summary or ''}\n{(document.extracted_text or '')[:6000]}"
        document.embedding = dumps_embedding(embed_text(text, prefer_openai=openai))
    session.flush()
    return len(documents)


def _priority_payload(priority: SourcePriority) -> dict:
    return {
        "source_id": priority.source.id,
        "domain": priority.source.canonical_domain,
        "status": priority.source.status,
        "score": round(priority.score, 4),
        "inbound_links": priority.inbound_links,
        "referring_sources": priority.referring_sources,
        "feed_signal": priority.feed_signal,
        "manual_seed_bonus": priority.manual_seed_bonus,
        "reason": priority.reason,
    }
