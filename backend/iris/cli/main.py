from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from urllib.parse import urlparse

import httpx

from iris.backfills.index_run_fk import migrate_index_run_fk
from iris.backfills.document_crawl_job_fk import migrate_document_crawl_job_fk
from iris.backfills.source_profiles import backfill_source_profiles
from iris.dao import db
from iris.dao import documents as documents_dao
from iris.dao import maintenance as maintenance_dao
from iris.dao import reporting as reporting_dao
from iris.dao import source_profiles as profile_dao
from iris.dao.db import init_db
from iris.dao.sources import get_or_create_source
from iris.models import (
    CrawlJob,
    IndexEvent,
    IndexRun,
    Source,
)
from iris.schemas.enums import CrawlJobStatus, IndexEventType, SourceStatus
from iris.schemas.indexing import PlannedSourceEvent, SourceFinishedEventPayload
from iris.services.common.config import (
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
    database_url,
)
from iris.services.indexing.indexer import plan_sources, autopilot
from iris.services.ingestion.crawler import Crawler
from iris.services.ingestion.document_classifier import analyze_document, classify_document
from iris.services.ingestion.embedding import document_embedding_text, dumps_embedding, embed_text
from iris.services.ingestion.source_classifier import (
    classify_source_homepage,
    classify_source_url,
)
from iris.services.retrieval.digest import get_digest
from iris.services.retrieval.search import search_documents, synthesize_answer
from iris.services.retrieval.source_profiles import generate_source_profile


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
        print(
            f"initialized postgresql://{parsed.hostname}:{parsed.port}/{parsed.path.lstrip('/')}"
        )
    else:
        print(f"initialized {database_url()}")


def cmd_seed(args: argparse.Namespace) -> None:
    with db.session_scope():
        classification = classify_source_url(args.url)
        source = get_or_create_source(
            args.url,
            status=SourceStatus.QUEUED.value,
            force_status=True,
        )
        source.description = classification.reason
        print(f"source {source.id}: {source.canonical_domain} ({source.status})")


def cmd_crawl(args: argparse.Namespace) -> None:
    with db.session_scope():
        classification = classify_source_url(args.url)
        source = get_or_create_source(
            args.url,
            status=SourceStatus.QUEUED.value,
            force_status=True,
        )
        source.description = classification.reason
        job = Crawler().crawl_source(
            source,
            max_pages=args.max_pages,
            max_depth=args.max_depth,
            skip_existing=args.skip_existing,
            max_documents=args.max_documents,
            active_pages=args.active_pages,
        )
        print(
            f"job {job.id} {job.status}: fetched={job.pages_fetched} failed={job.pages_failed} "
            f"docs={job.documents_indexed} links={job.links_seen} discovered_sources={job.sources_discovered}"
        )
        if job.error:
            print(job.error)


def cmd_search(args: argparse.Namespace) -> None:
    with db.session_scope():
        _search_row, ranked = search_documents(
            args.query, limit=args.limit, persist=False
        )
        print(synthesize_answer(args.query, ranked))
        for idx, item in enumerate(ranked, start=1):
            doc = item.document
            print(f"\n{idx}. {doc.title or doc.url}")
            print(
                f"   {doc.source.canonical_domain} | score={item.score:.3f} | {item.reason}"
            )
            print(f"   {doc.url}")
            if doc.summary:
                print(f"   {doc.summary[:260]}")


def cmd_digest(args: argparse.Namespace) -> None:
    with db.session_scope():
        items = get_digest(limit=args.limit)
        for idx, item in enumerate(items, start=1):
            doc = item.document
            print(f"{idx}. {doc.title or doc.url}")
            print(f"   {doc.source.canonical_domain} | score={item.score:.3f}")
            print(f"   {item.reason}")


def cmd_status(_args: argparse.Namespace) -> None:
    with db.session_scope():
        print("sources")
        for status, count in reporting_dao.count_sources_by_status():
            print(f"  {status}: {count}")
        print("documents")
        for doc_type, status, count in reporting_dao.count_documents_by_type_status():
            print(f"  {doc_type}/{status}: {count}")
        print(f"links: {reporting_dao.count_links()}")
        print(f"resolved links: {reporting_dao.count_resolved_links()}")
        latest_jobs = reporting_dao.get_latest_crawl_jobs()
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
    with db.session_scope():
        for row in reporting_dao.get_sql_rows(args.query):
            print(tuple(row))


def cmd_classify_sources(args: argparse.Namespace) -> None:
    with db.session_scope():
        sources = maintenance_dao.get_queued_sources(args.limit)
        changed = 0
        ignored = 0
        for source in sources:
            classification = classify_source_for_cli(source)
            if (
                source.status != classification.status
                or source.description != classification.reason
            ):
                source.status = classification.status
                source.description = classification.reason
                changed += 1
            if source.status == SourceStatus.IGNORED.value:
                ignored += 1
        print(f"classified={len(sources)} changed={changed} ignored={ignored}")


def classify_source_for_cli(source: Source):
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            response = client.get(source.url)
            response.raise_for_status()
        return classify_source_homepage(str(response.url), response.text)
    except Exception as exc:
        logging.getLogger("iris.cli").warning(
            "Could not fetch homepage for %s: %s", source.canonical_domain, exc
        )
        return classify_source_url(source.url)


def cmd_classify_source(args: argparse.Namespace) -> None:
    with db.session_scope():
        source = get_or_create_source(
            args.url, status=SourceStatus.QUEUED.value, force_status=args.force
        )
        classification = classify_source_for_cli(source)
        if classification.status == SourceStatus.IGNORED.value:
            source.status = SourceStatus.IGNORED.value
        elif (
            source.status in {SourceStatus.IGNORED.value, SourceStatus.FAILED.value}
            or args.force
        ):
            source.status = SourceStatus.QUEUED.value
        source.description = classification.reason
        print(f"source {source.id}: {source.canonical_domain} status={source.status}")
        print(source.description)


def cmd_set_source_ignored(args: argparse.Namespace) -> None:
    with db.session_scope():
        source, deleted_docs = maintenance_dao.set_source_ignored(
            args.domain, reason=args.reason, delete_rows=args.delete_rows
        )
        if not source:
            print(f"source not found: {args.domain}")
            return
        print(
            f"ignored source {source.id}: {source.canonical_domain}; deleted_docs={deleted_docs}"
        )


def cmd_embed_documents(args: argparse.Namespace) -> None:
    with db.session_scope():
        documents = maintenance_dao.get_documents_for_embedding(
            missing_only=args.missing_only, limit=args.limit
        )
        for idx, document in enumerate(documents, start=1):
            text = document_embedding_text(
                title=document.title,
                summary=document.summary,
                topics=document.topics,
                extracted_text=document.extracted_text,
            )
            document.embedding = dumps_embedding(
                embed_text(text, prefer_openai=args.openai)
            )
            if idx % 10 == 0:
                db.flush()
                print(f"embedded={idx}/{len(documents)}")
        print(f"embedded={len(documents)}")


def cmd_audit_documents(args: argparse.Namespace) -> None:
    with db.session_scope():
        print("document counts")
        for domain, doc_type, count in reporting_dao.count_documents_by_source_type():
            if args.source and domain != args.source:
                continue
            print(f"  {domain} {doc_type}: {count}")

        documents = maintenance_dao.get_fetched_documents(
            source_domain=args.source, limit=args.limit
        )
        print("samples")
        for doc in documents:
            link_count = reporting_dao.count_document_links(doc.id)
            classification = classify_document(
                url=doc.url,
                title=doc.title,
                text=doc.extracted_text or "",
                link_count=link_count,
                has_author=bool(doc.author),
                has_published_date=bool(doc.published_at),
            )
            flag = (
                "OK"
                if classification.document_type == doc.document_type
                else "RECLASSIFY"
            )
            print(
                f"  {flag} doc={doc.id} {doc.source.canonical_domain} "
                f"{doc.document_type}->{classification.document_type} "
                f"links={link_count} title={doc.title or doc.url}"
            )
            if args.verbose:
                print(f"    {classification.reason}")


def cmd_reclassify_documents(args: argparse.Namespace) -> None:
    with db.session_scope():
        documents = maintenance_dao.get_fetched_documents(
            source_domain=args.source, limit=args.limit
        )
        changed = 0
        for doc in documents:
            link_count = reporting_dao.count_document_links(doc.id)
            analysis = analyze_document(
                url=doc.url,
                metadata_title=doc.title,
                text=doc.extracted_text or "",
                link_count=link_count,
                has_author=bool(doc.author),
                has_published_date=bool(doc.published_at),
            )
            if (
                doc.document_type != analysis.document_type
                or doc.title != analysis.title
                or (doc.summary or "") != analysis.summary
                or (doc.topics or []) != analysis.topics
            ):
                changed += 1
                print(
                    f"doc {doc.id}: type {doc.document_type}->{analysis.document_type} "
                    f"title {doc.title or doc.url!r}->{analysis.title!r}"
                )
                if not args.dry_run:
                    documents_dao.update_document_analysis(doc, analysis)
        print(f"checked={len(documents)} changed={changed} dry_run={args.dry_run}")


def cmd_source_priorities(args: argparse.Namespace) -> None:
    with db.session_scope():
        priorities = plan_sources(
            limit=args.limit,
            seed_domain=args.seed_domain,
        )
        for idx, item in enumerate(priorities, start=1):
            source = item.source
            print(
                f"{idx}. {source.canonical_domain} score={item.score:.3f} "
                f"status={source.status}"
            )
            print(f"   {item.reason}")


def cmd_autopilot(args: argparse.Namespace) -> None:
    print(
        "autopilot starting: "
        f"budget_sources={args.budget_sources} max_pages={args.max_pages} max_depth={args.max_depth} "
        f"max_documents_per_source={args.max_documents_per_source or 'none'} "
        f"seed_domain={args.seed_domain or 'none'} "
        f"skip_existing={bool(args.skip_existing)} active_pages={args.active_pages} dry_run={bool(args.dry_run)}",
        flush=True,
    )
    run = autopilot(
        budget_sources=args.budget_sources,
        max_pages=args.max_pages,
        max_depth=args.max_depth,
        max_documents_per_source=args.max_documents_per_source,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        openai_embeddings=True if args.openai_embeddings else None,
        seed_domain=args.seed_domain,
        active_pages=args.active_pages,
    )
    print(
        f"index_run {run.id} {run.status}: planned={run.planned_sources} attempted={run.attempted_sources} "
        f"crawled={run.crawled_sources} ignored={run.ignored_sources} docs={run.documents_indexed} "
        f"links={run.links_seen} discovered={run.sources_discovered} errors={run.errors}"
    )
    if run.stop_reason:
        print(f"stop_reason={run.stop_reason}")
    with db.session_scope():
        events = reporting_dao.get_index_events(run.id, limit=args.show_events)
        for event in events:
            print(f"  [{event.event_type}] {event.message}")
            if event.payload and args.verbose_events:
                print(f"    {event.payload[:1000]}")


def cmd_index_runs(args: argparse.Namespace) -> None:
    with db.session_scope():
        runs = reporting_dao.get_latest_index_runs(args.limit)
        for run in runs:
            crawl_count = reporting_dao.count_crawl_jobs_for_run(run.id)
            print(
                f"{run.id}. {run.status} dry_run={bool(run.dry_run)} started={run.started_at} "
                f"planned={run.planned_sources} attempted={run.attempted_sources} crawled={run.crawled_sources} "
                f"ignored={run.ignored_sources} crawl_jobs={crawl_count} docs={run.documents_indexed} errors={run.errors}"
            )
            if run.stop_reason:
                print(f"   stop_reason={run.stop_reason}")


def cmd_get_index_events(args: argparse.Namespace) -> None:
    with db.session_scope():
        events = reporting_dao.get_index_events(args.run_id, limit=args.limit)
        for event in events:
            print(
                f"{event.created_at} [{event.event_type}] source={event.source_id} crawl={event.crawl_job_id} {event.message}"
            )
            if event.payload:
                print(f"  {event.payload[: args.payload_chars]}")


def cmd_index_summary(args: argparse.Namespace) -> None:
    with db.session_scope():
        run = reporting_dao.get_index_run(args.run_id)
        if not run:
            print(f"index_run not found: {args.run_id}")
            return
        events = reporting_dao.get_index_events(run.id)
        jobs = reporting_dao.get_crawl_jobs_for_index_run(run.id)
        jobs_by_source_id = {source.id: job for job, source in jobs}
        sources_by_id = {source.id: source for _job, source in jobs}

        plan = _planned_sources_from_events(events)
        started_source_ids = [
            event.source_id
            for event in events
            if event.event_type == IndexEventType.SOURCE_STARTED.value
            and event.source_id
        ]
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

        rows = (
            plan
            if args.all
            else [item for item in plan if item.source_id in set(started_source_ids)]
        )
        if not rows:
            rows = [
                PlannedSourceEvent(
                    source_id=source_id,
                    domain=sources_by_id.get(source_id).canonical_domain
                    if sources_by_id.get(source_id)
                    else str(source_id),
                )
                for source_id in started_source_ids
            ]
        for idx, item in enumerate(rows, start=1):
            source_id = item.source_id
            domain = item.domain or (
                sources_by_id.get(source_id).canonical_domain
                if source_id in sources_by_id
                else f"source:{source_id}"
            )
            job = jobs_by_source_id.get(source_id)
            payload = finished_payloads.get(source_id, SourceFinishedEventPayload())
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
                print(
                    f"  {idx:>2}. {domain:<28} interrupted_before_job     fetched=0   docs=0   links=0      discovered=0"
                )
            else:
                score = item.score
                reason = item.reason
                score_text = (
                    f" score={score:.3f}" if isinstance(score, (int, float)) else ""
                )
                print(f"  {idx:>2}. {domain:<28} not_attempted{score_text} {reason}")


def _planned_sources_from_events(events: list[IndexEvent]) -> list[PlannedSourceEvent]:
    for event in events:
        if event.event_type != IndexEventType.PLAN_CREATED.value or not event.payload:
            continue
        try:
            payload = json.loads(event.payload)
        except json.JSONDecodeError:
            return []
        sources = payload.get("sources", [])
        if not isinstance(sources, list):
            return []
        planned: list[PlannedSourceEvent] = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            source_id = source.get("source_id")
            domain = source.get("domain")
            if not isinstance(source_id, int) or not isinstance(domain, str):
                continue
            score = source.get("score")
            planned.append(
                PlannedSourceEvent(
                    source_id=source_id,
                    domain=domain,
                    score=float(score) if isinstance(score, (int, float)) else None,
                    reason=str(source.get("reason", "")),
                )
            )
        return planned
    return []


def _finished_payloads_by_source(
    events: list[IndexEvent],
) -> dict[int, SourceFinishedEventPayload]:
    payloads: dict[int, SourceFinishedEventPayload] = {}
    for event in events:
        if (
            event.event_type != IndexEventType.SOURCE_FINISHED.value
            or not event.source_id
            or not event.payload
        ):
            continue
        try:
            payload = json.loads(event.payload)
        except json.JSONDecodeError:
            payload = {}
        payloads[event.source_id] = SourceFinishedEventPayload(
            max_documents_per_source=payload.get("max_documents_per_source")
            if isinstance(payload, dict)
            else None,
        )
    return payloads


def _crawl_outcome(
    run: IndexRun, job: CrawlJob, payload: SourceFinishedEventPayload
) -> str:
    if job.status == CrawlJobStatus.SKIPPED.value:
        return "rejected"
    if job.status == CrawlJobStatus.FAILED.value:
        return "failed"
    if job.status != CrawlJobStatus.SUCCEEDED.value:
        return job.status
    max_documents = payload.max_documents_per_source
    if max_documents and job.documents_indexed >= int(max_documents):
        return "hit_max_documents"
    if run.max_pages and job.pages_fetched >= run.max_pages:
        return "hit_max_pages"
    return "exhausted"


def cmd_migrate_index_run_fk(_args: argparse.Namespace) -> None:
    with db.session_scope():
        print(f"backfilled={migrate_index_run_fk()}")


def cmd_migrate_document_crawl_job_fk(_args: argparse.Namespace) -> None:
    with db.session_scope():
        print(f"backfilled={migrate_document_crawl_job_fk()}")


def cmd_generate_source_profile(args: argparse.Namespace) -> None:
    with db.session_scope():
        source = profile_dao.get_source_by_domain(args.domain)
        if not source:
            print(f"source not found: {args.domain}")
            return
        analysis = generate_source_profile(source, force=args.force)
        print(
            f"profile source={source.canonical_domain} status={analysis.status} "
            f"display_name={analysis.display_name or 'none'}"
        )
        if analysis.error:
            print(f"error={analysis.error}")


def cmd_backfill_source_profiles(args: argparse.Namespace) -> None:
    with db.session_scope():
        result = backfill_source_profiles(limit=args.limit or None, force=args.force)
        print(
            f"profiles checked={result.checked} succeeded={result.succeeded} "
            f"missing_key={result.missing_key} failed={result.failed}"
        )


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
    crawl.add_argument("--active-pages", type=int, default=4)
    crawl.add_argument("--skip-existing", action="store_true")
    crawl.set_defaults(func=cmd_crawl)

    search = subparsers.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.set_defaults(func=cmd_search)

    digest = subparsers.add_parser("digest")
    digest.add_argument("--limit", type=int, default=10)
    digest.set_defaults(func=cmd_digest)

    status = subparsers.add_parser("status")
    status.set_defaults(func=cmd_status)

    classify = subparsers.add_parser("classify-sources")
    classify.add_argument("--limit", type=int, default=0)
    classify.set_defaults(func=cmd_classify_sources)

    classify_one = subparsers.add_parser("classify-source")
    classify_one.add_argument("url")
    classify_one.add_argument("--force", action="store_true")
    classify_one.set_defaults(func=cmd_classify_source)

    ignore = subparsers.add_parser("ignore-source")
    ignore.add_argument("domain")
    ignore.add_argument("--reason", default="manually ignored")
    ignore.add_argument("--delete-rows", action="store_true")
    ignore.set_defaults(func=cmd_set_source_ignored)

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
    priorities.add_argument("--seed-domain", default=None)
    priorities.set_defaults(func=cmd_source_priorities)

    autopilot = subparsers.add_parser("autopilot")
    autopilot.add_argument("--budget-sources", type=int, default=5)
    autopilot.add_argument("--max-pages", type=int, default=40)
    autopilot.add_argument("--max-depth", type=int, default=2)
    autopilot.add_argument("--max-documents-per-source", type=int, default=None)
    autopilot.add_argument("--active-pages", type=int, default=4)
    autopilot.add_argument("--skip-existing", action="store_true")
    autopilot.add_argument("--dry-run", action="store_true")
    autopilot.add_argument("--openai-embeddings", action="store_true")
    autopilot.add_argument("--seed-domain", default=None)
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
    index_events.set_defaults(func=cmd_get_index_events)

    index_summary = subparsers.add_parser("index-summary")
    index_summary.add_argument("run_id", type=int)
    index_summary.add_argument(
        "--all",
        action="store_true",
        help="include planned sources that were not attempted",
    )
    index_summary.add_argument(
        "--reasons",
        action="store_true",
        help="show first-line rejection/failure reasons",
    )
    index_summary.set_defaults(func=cmd_index_summary)

    migrate_index_fk = subparsers.add_parser("migrate-index-run-fk")
    migrate_index_fk.set_defaults(func=cmd_migrate_index_run_fk)

    migrate_document_job_fk = subparsers.add_parser("migrate-document-crawl-job-fk")
    migrate_document_job_fk.set_defaults(func=cmd_migrate_document_crawl_job_fk)

    source_profile = subparsers.add_parser("generate-source-profile")
    source_profile.add_argument("domain")
    source_profile.add_argument("--force", action="store_true")
    source_profile.set_defaults(func=cmd_generate_source_profile)

    source_profile_backfill = subparsers.add_parser("backfill-source-profiles")
    source_profile_backfill.add_argument("--limit", type=int, default=0)
    source_profile_backfill.add_argument("--force", action="store_true")
    source_profile_backfill.set_defaults(func=cmd_backfill_source_profiles)

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
