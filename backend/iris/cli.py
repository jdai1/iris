from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from urllib.parse import urlparse

import httpx
from sqlalchemy import delete, func, select, text, update

from iris.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT, database_url
from iris.crawler import crawl_source
from iris.db import init_db, session_scope
from iris.digest import get_digest, populate_digest
from iris.document_classifier import classify_document
from iris.indexer import plan_sources, run_autopilot
from iris.models import CrawlJob, Document, IndexEvent, IndexRun, Link, Source
from iris.repository import get_or_create_source
from iris.source_classifier import classify_source_homepage, classify_source_url
from iris.embedding import dumps_embedding, embed_text
from iris.search import search_documents


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def cmd_init_db(_args: argparse.Namespace) -> None:
    init_db()
    parsed = urlparse(database_url())
    if parsed.scheme.startswith("postgresql"):
        print(f"initialized postgresql://{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}")
    else:
        print(f"initialized {database_url()}")


def cmd_seed(args: argparse.Namespace) -> None:
    with session_scope() as session:
        classification = classify_source_url(args.url)
        source = get_or_create_source(
            session,
            args.url,
            status="queued",
            source_type=classification.source_type,
            force_status=True,
        )
        print(f"source {source.id}: {source.canonical_domain} ({source.status}, {source.source_type})")


def cmd_crawl(args: argparse.Namespace) -> None:
    with session_scope() as session:
        classification = classify_source_url(args.url)
        source = get_or_create_source(
            session,
            args.url,
            status="queued",
            source_type=classification.source_type,
            force_status=True,
        )
        job = crawl_source(
            session,
            source,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            skip_existing=args.skip_existing,
            max_documents=args.max_documents,
        )
        print(
            f"job {job.id} {job.status}: fetched={job.pages_fetched} failed={job.pages_failed} "
            f"docs={job.documents_indexed} links={job.links_seen} discovered_sources={job.sources_discovered}"
        )
        if job.error:
            print(job.error)


def cmd_search(args: argparse.Namespace) -> None:
    with session_scope() as session:
        search_row, ranked = search_documents(session, args.query, limit=args.limit, persist=True)
        print(search_row.answer if search_row else "")
        for idx, item in enumerate(ranked, start=1):
            doc = item.document
            print(f"\n{idx}. {doc.title or doc.final_url}")
            print(f"   {doc.source.canonical_domain} | score={item.score:.3f} | {item.reason}")
            print(f"   {doc.final_url}")
            if doc.summary:
                print(f"   {doc.summary[:260]}")


def cmd_digest(args: argparse.Namespace) -> None:
    with session_scope() as session:
        if args.populate:
            populate_digest(session, limit=args.limit)
        items = get_digest(session, limit=args.limit)
        for idx, item in enumerate(items, start=1):
            doc = item.document
            print(f"{idx}. {doc.title or doc.final_url}")
            print(f"   {doc.source.canonical_domain} | score={item.score:.3f}")
            print(f"   {item.reason}")


def cmd_status(_args: argparse.Namespace) -> None:
    with session_scope() as session:
        print("sources")
        for status, count in session.execute(select(Source.status, func.count(Source.id)).group_by(Source.status)):
            print(f"  {status}: {count}")
        print("source types")
        for source_type, count in session.execute(select(Source.source_type, func.count(Source.id)).group_by(Source.source_type)):
            print(f"  {source_type}: {count}")
        print("documents")
        for doc_type, status, count in session.execute(
            select(Document.document_type, Document.crawl_status, func.count(Document.id)).group_by(
                Document.document_type, Document.crawl_status
            )
        ):
            print(f"  {doc_type}/{status}: {count}")
        print(f"links: {session.scalar(select(func.count(Link.id)))}")
        print(f"resolved links: {session.scalar(select(func.count(Link.id)).where(Link.target_document_id.is_not(None)))}")
        latest_jobs = session.execute(select(CrawlJob).order_by(CrawlJob.started_at.desc()).limit(5)).scalars().all()
        print("latest crawl jobs")
        for job in latest_jobs:
            print(
                f"  {job.id} source={job.source_id} {job.status} fetched={job.pages_fetched} "
                f"failed={job.pages_failed} docs={job.documents_indexed} links={job.links_seen}"
            )


def cmd_sql(args: argparse.Namespace) -> None:
    url = database_url()
    if url.startswith("postgresql"):
        command = ["psql", url]
        if args.query:
            command.extend(["-c", args.query])
        subprocess.run(command, check=False)
        return
    with session_scope() as session:
        for row in session.execute(text(args.query)):
            print(tuple(row))


def cmd_classify_sources(args: argparse.Namespace) -> None:
    with session_scope() as session:
        statement = select(Source).where(Source.status == "queued").order_by(Source.first_seen_at.asc())
        if args.limit:
            statement = statement.limit(args.limit)
        sources = session.execute(statement).scalars().all()
        changed = 0
        ignored = 0
        for source in sources:
            classification = classify_source_for_cli(source)
            if source.status != classification.status or (
                source.source_type == "unknown" and classification.source_type != "unknown"
            ):
                source.status = classification.status
                if source.source_type == "unknown" or args.overwrite_type:
                    source.source_type = classification.source_type
                source.quality_score = classification.confidence
                source.description = classification.reason
                changed += 1
            if source.status == "ignored":
                ignored += 1
        print(f"classified={len(sources)} changed={changed} ignored={ignored}")


def classify_source_for_cli(source: Source):
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.get(source.homepage_url)
            response.raise_for_status()
        return classify_source_homepage(str(response.url), response.text)
    except Exception as exc:
        logging.getLogger("iris.cli").warning("Could not fetch homepage for %s: %s", source.canonical_domain, exc)
        return classify_source_url(source.homepage_url)


def cmd_classify_source(args: argparse.Namespace) -> None:
    with session_scope() as session:
        source = get_or_create_source(session, args.url, status="queued", force_status=args.force)
        classification = classify_source_for_cli(source)
        if classification.status == "ignored":
            source.status = "ignored"
        elif source.status in {"ignored", "failed"} or args.force:
            source.status = "queued"
        source.source_type = classification.source_type
        source.quality_score = classification.confidence
        source.description = classification.reason
        print(
            f"source {source.id}: {source.canonical_domain} "
            f"status={source.status} type={source.source_type} confidence={source.quality_score}"
        )
        print(source.description)


def cmd_ignore_source(args: argparse.Namespace) -> None:
    with session_scope() as session:
        domain = args.domain
        if "://" in domain:
            domain = urlparse(domain).netloc
        domain = domain.lower().removeprefix("www.")
        source = session.execute(select(Source).where(Source.canonical_domain == domain)).scalar_one_or_none()
        if not source:
            print(f"source not found: {domain}")
            return
        document_ids = list(session.scalars(select(Document.id).where(Document.source_id == source.id)))
        if args.delete_rows and document_ids:
            session.execute(delete(Link).where(Link.source_document_id.in_(document_ids)))
            session.execute(delete(Link).where(Link.target_document_id.in_(document_ids)))
            session.execute(delete(Document).where(Document.id.in_(document_ids)))
        session.execute(update(Link).where(Link.target_source_id == source.id).values(target_source_id=None))
        source.status = "ignored"
        source.source_type = args.source_type
        source.description = args.reason
        print(f"ignored source {source.id}: {source.canonical_domain}; deleted_docs={len(document_ids) if args.delete_rows else 0}")


def cmd_embed_documents(args: argparse.Namespace) -> None:
    with session_scope() as session:
        statement = (
            select(Document)
            .where(Document.document_type == "essay")
            .where(Document.crawl_status == "fetched")
            .order_by(Document.last_crawled_at.desc())
        )
        if args.missing_only:
            statement = statement.where(Document.embedding.is_(None))
        if args.limit:
            statement = statement.limit(args.limit)
        documents = session.execute(statement).scalars().all()
        for idx, document in enumerate(documents, start=1):
            text = f"{document.title or ''}\n{document.summary or ''}\n{(document.extracted_text or '')[:6000]}"
            document.embedding = dumps_embedding(embed_text(text, prefer_openai=args.openai))
            if idx % 10 == 0:
                session.flush()
                print(f"embedded={idx}/{len(documents)}")
        print(f"embedded={len(documents)}")


def cmd_audit_documents(args: argparse.Namespace) -> None:
    with session_scope() as session:
        print("document counts")
        rows = session.execute(
            select(Source.canonical_domain, Document.document_type, func.count(Document.id))
            .join(Source, Document.source_id == Source.id)
            .group_by(Source.canonical_domain, Document.document_type)
            .order_by(Source.canonical_domain, Document.document_type)
        ).all()
        for domain, doc_type, count in rows:
            if args.source and domain != args.source:
                continue
            print(f"  {domain} {doc_type}: {count}")

        statement = (
            select(Document)
            .join(Source, Document.source_id == Source.id)
            .where(Document.crawl_status == "fetched")
            .order_by(Document.quality_score.asc().nullsfirst(), Document.last_crawled_at.desc())
        )
        if args.source:
            statement = statement.where(Source.canonical_domain == args.source)
        if args.limit:
            statement = statement.limit(args.limit)
        documents = session.execute(statement).scalars().all()
        print("samples")
        for doc in documents:
            link_count = session.scalar(select(func.count(Link.id)).where(Link.source_document_id == doc.id)) or 0
            classification = classify_document(
                url=doc.final_url,
                title=doc.title,
                text=doc.extracted_text or "",
                link_count=link_count,
                has_author=bool(doc.author),
                has_published_date=bool(doc.published_at),
            )
            flag = "OK" if classification.document_type == doc.document_type else "RECLASSIFY"
            print(
                f"  {flag} doc={doc.id} {doc.source.canonical_domain} "
                f"{doc.document_type}->{classification.document_type} quality={doc.quality_score} "
                f"links={link_count} title={doc.title or doc.final_url}"
            )
            if args.verbose:
                print(f"    {classification.reason}")


def cmd_reclassify_documents(args: argparse.Namespace) -> None:
    with session_scope() as session:
        statement = select(Document).join(Source, Document.source_id == Source.id).where(Document.crawl_status == "fetched")
        if args.source:
            statement = statement.where(Source.canonical_domain == args.source)
        if args.limit:
            statement = statement.limit(args.limit)
        documents = session.execute(statement).scalars().all()
        changed = 0
        for doc in documents:
            link_count = session.scalar(select(func.count(Link.id)).where(Link.source_document_id == doc.id)) or 0
            classification = classify_document(
                url=doc.final_url,
                title=doc.title,
                text=doc.extracted_text or "",
                link_count=link_count,
                has_author=bool(doc.author),
                has_published_date=bool(doc.published_at),
            )
            if doc.document_type != classification.document_type or doc.quality_score != classification.quality_score:
                changed += 1
                print(
                    f"doc {doc.id}: {doc.document_type}->{classification.document_type} "
                    f"quality {doc.quality_score}->{classification.quality_score:.3f} "
                    f"{doc.title or doc.final_url}"
                )
                if not args.dry_run:
                    doc.document_type = classification.document_type
                    doc.quality_score = classification.quality_score
        print(f"checked={len(documents)} changed={changed} dry_run={args.dry_run}")


def cmd_source_priorities(args: argparse.Namespace) -> None:
    with session_scope() as session:
        priorities = plan_sources(session, limit=args.limit)
        for idx, item in enumerate(priorities, start=1):
            source = item.source
            print(
                f"{idx}. {source.canonical_domain} score={item.score:.3f} "
                f"status={source.status} type={source.source_type}"
            )
            print(f"   {item.reason}")


def cmd_autopilot(args: argparse.Namespace) -> None:
    print(
        "autopilot starting: "
        f"budget_sources={args.budget_sources} max_pages={args.max_pages} max_depth={args.max_depth} "
        f"max_documents_per_source={args.max_documents_per_source or 'none'} "
        f"skip_existing={bool(args.skip_existing)} embed={not args.no_embed} dry_run={bool(args.dry_run)}",
        flush=True,
    )
    run = run_autopilot(
        budget_sources=args.budget_sources,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_documents_per_source=args.max_documents_per_source,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        embed=not args.no_embed,
        openai_embeddings=True if args.openai_embeddings else None,
    )
    print(
        f"index_run {run.id} {run.status}: planned={run.planned_sources} attempted={run.attempted_sources} "
        f"crawled={run.crawled_sources} ignored={run.ignored_sources} docs={run.documents_indexed} "
        f"links={run.links_seen} discovered={run.sources_discovered} errors={run.errors}"
    )
    if run.stop_reason:
        print(f"stop_reason={run.stop_reason}")
    with session_scope() as session:
        events = session.execute(
            select(IndexEvent)
            .where(IndexEvent.index_run_id == run.id)
            .order_by(IndexEvent.created_at.asc())
            .limit(args.show_events)
        ).scalars().all()
        for event in events:
            print(f"  [{event.event_type}] {event.message}")
            if event.payload and args.verbose_events:
                print(f"    {event.payload[:1000]}")


def cmd_index_runs(args: argparse.Namespace) -> None:
    with session_scope() as session:
        runs = session.execute(select(IndexRun).order_by(IndexRun.started_at.desc()).limit(args.limit)).scalars().all()
        for run in runs:
            crawl_count = session.scalar(select(func.count(CrawlJob.id)).where(CrawlJob.index_run_id == run.id)) or 0
            print(
                f"{run.id}. {run.status} dry_run={bool(run.dry_run)} started={run.started_at} "
                f"planned={run.planned_sources} attempted={run.attempted_sources} crawled={run.crawled_sources} "
                f"ignored={run.ignored_sources} crawl_jobs={crawl_count} docs={run.documents_indexed} errors={run.errors}"
            )
            if run.stop_reason:
                print(f"   stop_reason={run.stop_reason}")


def cmd_index_events(args: argparse.Namespace) -> None:
    with session_scope() as session:
        events = session.execute(
            select(IndexEvent)
            .where(IndexEvent.index_run_id == args.run_id)
            .order_by(IndexEvent.created_at.asc())
            .limit(args.limit)
        ).scalars().all()
        for event in events:
            print(f"{event.created_at} [{event.event_type}] source={event.source_id} crawl={event.crawl_job_id} {event.message}")
            if event.payload:
                print(f"  {event.payload[:args.payload_chars]}")


def cmd_index_summary(args: argparse.Namespace) -> None:
    with session_scope() as session:
        run = session.get(IndexRun, args.run_id)
        if not run:
            print(f"index_run not found: {args.run_id}")
            return
        events = session.execute(
            select(IndexEvent)
            .where(IndexEvent.index_run_id == run.id)
            .order_by(IndexEvent.created_at.asc())
        ).scalars().all()
        jobs = session.execute(
            select(CrawlJob, Source)
            .join(Source, CrawlJob.source_id == Source.id)
            .where(CrawlJob.index_run_id == run.id)
            .order_by(CrawlJob.started_at.asc())
        ).all()
        jobs_by_source_id = {source.id: job for job, source in jobs}
        sources_by_id = {source.id: source for _job, source in jobs}

        plan = _planned_sources_from_events(events)
        started_source_ids = [event.source_id for event in events if event.event_type == "source_started" and event.source_id]
        finished_payloads = _finished_payloads_by_source(events)

        print(
            f"index_run {run.id}: {run.status} stop={run.stop_reason or 'none'} "
            f"started={run.started_at} finished={run.finished_at}"
        )
        print(
            f"planned={run.planned_sources} attempted={run.attempted_sources} "
            f"jobs={len(jobs)} crawled={run.crawled_sources} ignored={run.ignored_sources} "
            f"errors={run.errors} docs={run.documents_indexed} links={run.links_seen} discovered={run.sources_discovered}"
        )
        print("sources")

        rows = plan if args.all else [item for item in plan if item.get("source_id") in set(started_source_ids)]
        if not rows:
            rows = [{"source_id": source_id, "domain": sources_by_id.get(source_id).canonical_domain if sources_by_id.get(source_id) else str(source_id)} for source_id in started_source_ids]
        for idx, item in enumerate(rows, start=1):
            source_id = item.get("source_id")
            domain = item.get("domain") or (sources_by_id.get(source_id).canonical_domain if source_id in sources_by_id else f"source:{source_id}")
            job = jobs_by_source_id.get(source_id)
            payload = finished_payloads.get(source_id, {})
            if job:
                outcome = _crawl_outcome(run, job, payload)
                print(
                    f"  {idx:>2}. {domain:<28} {outcome:<24} "
                    f"fetched={job.pages_fetched:<3} docs={job.documents_indexed:<3} "
                    f"links={job.links_seen:<6} discovered={job.sources_discovered:<4}"
                )
                if args.reasons and job.error:
                    print(f"      {job.error.splitlines()[0][:220]}")
            elif source_id in started_source_ids:
                print(f"  {idx:>2}. {domain:<28} interrupted_before_job     fetched=0   docs=0   links=0      discovered=0")
            else:
                score = item.get("score")
                reason = item.get("reason", "")
                score_text = f" score={score:.3f}" if isinstance(score, (int, float)) else ""
                print(f"  {idx:>2}. {domain:<28} not_attempted{score_text} {reason}")


def _planned_sources_from_events(events: list[IndexEvent]) -> list[dict]:
    for event in events:
        if event.event_type != "plan_created" or not event.payload:
            continue
        try:
            payload = json.loads(event.payload)
        except json.JSONDecodeError:
            return []
        sources = payload.get("sources", [])
        return sources if isinstance(sources, list) else []
    return []


def _finished_payloads_by_source(events: list[IndexEvent]) -> dict[int, dict]:
    payloads: dict[int, dict] = {}
    for event in events:
        if event.event_type != "source_finished" or not event.source_id or not event.payload:
            continue
        try:
            payloads[event.source_id] = json.loads(event.payload)
        except json.JSONDecodeError:
            payloads[event.source_id] = {}
    return payloads


def _crawl_outcome(run: IndexRun, job: CrawlJob, payload: dict) -> str:
    if job.status == "skipped":
        return "rejected"
    if job.status == "failed":
        return "failed"
    if job.status != "succeeded":
        return job.status
    max_documents = payload.get("max_documents_per_source")
    if max_documents and job.documents_indexed >= int(max_documents):
        return "hit_max_documents"
    if run.max_pages and job.pages_fetched >= run.max_pages:
        return "hit_max_pages"
    return "exhausted"


def cmd_migrate_index_run_fk(_args: argparse.Namespace) -> None:
    with session_scope() as session:
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
        print(f"backfilled={result.rowcount}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="iris")
    parser.add_argument("--verbose", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init-db")
    init.set_defaults(func=cmd_init_db)

    seed = subparsers.add_parser("seed")
    seed.add_argument("url")
    seed.set_defaults(func=cmd_seed)

    crawl = subparsers.add_parser("crawl")
    crawl.add_argument("url")
    crawl.add_argument("--max-pages", type=int, default=80)
    crawl.add_argument("--max-depth", type=int, default=3)
    crawl.add_argument("--max-documents", type=int, default=None)
    crawl.add_argument("--skip-existing", action="store_true")
    crawl.set_defaults(func=cmd_crawl)

    search = subparsers.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)

    digest = subparsers.add_parser("digest")
    digest.add_argument("--limit", type=int, default=10)
    digest.add_argument("--populate", action="store_true")
    digest.set_defaults(func=cmd_digest)

    status = subparsers.add_parser("status")
    status.set_defaults(func=cmd_status)

    classify = subparsers.add_parser("classify-sources")
    classify.add_argument("--limit", type=int, default=0)
    classify.add_argument("--overwrite-type", action="store_true")
    classify.set_defaults(func=cmd_classify_sources)

    classify_one = subparsers.add_parser("classify-source")
    classify_one.add_argument("url")
    classify_one.add_argument("--force", action="store_true")
    classify_one.set_defaults(func=cmd_classify_source)

    ignore = subparsers.add_parser("ignore-source")
    ignore.add_argument("domain")
    ignore.add_argument("--source-type", default="ignored")
    ignore.add_argument("--reason", default="manually ignored")
    ignore.add_argument("--delete-rows", action="store_true")
    ignore.set_defaults(func=cmd_ignore_source)

    embed = subparsers.add_parser("embed-documents")
    embed.add_argument("--limit", type=int, default=0)
    embed.add_argument("--missing-only", action="store_true")
    embed.add_argument("--openai", action="store_true")
    embed.set_defaults(func=cmd_embed_documents)

    audit_docs = subparsers.add_parser("audit-documents")
    audit_docs.add_argument("--source")
    audit_docs.add_argument("--limit", type=int, default=30)
    audit_docs.add_argument("--verbose", action="store_true")
    audit_docs.set_defaults(func=cmd_audit_documents)

    reclassify_docs = subparsers.add_parser("reclassify-documents")
    reclassify_docs.add_argument("--source")
    reclassify_docs.add_argument("--limit", type=int, default=0)
    reclassify_docs.add_argument("--dry-run", action="store_true")
    reclassify_docs.set_defaults(func=cmd_reclassify_documents)

    priorities = subparsers.add_parser("source-priorities")
    priorities.add_argument("--limit", type=int, default=20)
    priorities.set_defaults(func=cmd_source_priorities)

    autopilot = subparsers.add_parser("autopilot")
    autopilot.add_argument("--budget-sources", type=int, default=5)
    autopilot.add_argument("--max-pages", type=int, default=40)
    autopilot.add_argument("--max-depth", type=int, default=2)
    autopilot.add_argument("--max-documents-per-source", type=int, default=None)
    autopilot.add_argument("--skip-existing", action="store_true")
    autopilot.add_argument("--dry-run", action="store_true")
    autopilot.add_argument("--embed", action="store_true", help=argparse.SUPPRESS)
    autopilot.add_argument("--no-embed", action="store_true")
    autopilot.add_argument("--openai-embeddings", action="store_true")
    autopilot.add_argument("--show-events", type=int, default=20)
    autopilot.add_argument("--verbose-events", action="store_true")
    autopilot.set_defaults(func=cmd_autopilot)

    index_runs = subparsers.add_parser("index-runs")
    index_runs.add_argument("--limit", type=int, default=10)
    index_runs.set_defaults(func=cmd_index_runs)

    index_events = subparsers.add_parser("index-events")
    index_events.add_argument("run_id", type=int)
    index_events.add_argument("--limit", type=int, default=100)
    index_events.add_argument("--payload-chars", type=int, default=1200)
    index_events.set_defaults(func=cmd_index_events)

    index_summary = subparsers.add_parser("index-summary")
    index_summary.add_argument("run_id", type=int)
    index_summary.add_argument("--all", action="store_true", help="include planned sources that were not attempted")
    index_summary.add_argument("--reasons", action="store_true", help="show first-line rejection/failure reasons")
    index_summary.set_defaults(func=cmd_index_summary)

    migrate_index_fk = subparsers.add_parser("migrate-index-run-fk")
    migrate_index_fk.set_defaults(func=cmd_migrate_index_run_fk)

    sql = subparsers.add_parser("sql")
    sql.add_argument("query", nargs="?", default="select 1")
    sql.set_defaults(func=cmd_sql)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    try:
        args.func(args)
        return 0
    except KeyboardInterrupt:
        print("\ninterrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
