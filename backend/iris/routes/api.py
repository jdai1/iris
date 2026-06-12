from __future__ import annotations

import json
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, joinedload

from iris.services.ingestion.crawler import Crawler
from iris.dao.db import SessionLocal, init_db
from iris.services.retrieval.digest import get_digest, populate_digest, record_feedback
from iris.models import CrawlJob, CrawlJobStatus, Document, DocumentType, IndexEvent, IndexEventType, IndexRun, Link, Source, SourceStatus
from iris.dao.core import get_or_create_source
from iris.schemas.api import CrawlSchema, DigestItemSchema, FeedbackSchema, GraphSchema, SearchSchema, SourceCreateSchema, SourceSchema
from iris.services.retrieval.search import search_documents, synthesize_answer
from iris.routes.dumps import dump_crawl_job, dump_digest_item, dump_document, dump_source
from iris.services.ingestion.source_classifier import classify_source_url


app = FastAPI(title="Iris", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_session():
    init_db()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict:
    source_count = session.scalar(select(func.count(Source.id)))
    document_count = session.scalar(select(func.count(Document.id)))
    return {"ok": True, "sources": source_count, "documents": document_count}


@app.post("/api/sources", response_model=SourceSchema)
def create_source(payload: SourceCreateSchema, session: Session = Depends(get_session)) -> SourceSchema:
    classification = classify_source_url(payload.url)
    source = get_or_create_source(
        session,
        payload.url,
        status=SourceStatus.QUEUED.value,
        force_status=True,
    )
    source.description = classification.reason
    if payload.crawl_now:
        Crawler(session).crawl_source(source, max_pages=payload.max_pages, max_depth=payload.max_depth)
    return dump_source(source)


@app.get("/api/sources", response_model=list[SourceSchema])
def list_sources(session: Session = Depends(get_session)) -> list[SourceSchema]:
    sources = session.execute(select(Source).order_by(Source.first_seen_at.desc())).scalars().all()
    return [dump_source(source) for source in sources]


@app.post("/api/sources/{source_id}/crawl", response_model=CrawlSchema)
def crawl_source_endpoint(source_id: int, max_pages: int = 80, max_depth: int = 3, session: Session = Depends(get_session)) -> CrawlSchema:
    source = session.get(Source, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    job = Crawler(session).crawl_source(source, max_pages=max_pages, max_depth=max_depth)
    return dump_crawl_job(job)


@app.get("/api/documents")
def list_documents(
    session: Session = Depends(get_session),
    limit: int = 50,
    offset: int = 0,
    source_id: int | None = None,
    document_type: str | None = None,
) -> dict:
    statement = select(Document).options(joinedload(Document.source)).order_by(Document.last_crawled_at.desc())
    if source_id:
        statement = statement.where(Document.source_id == source_id)
    if document_type and document_type != "all":
        statement = statement.where(Document.document_type == document_type)
    total = _count_statement(session, statement)
    documents = session.execute(statement.limit(_clamped_limit(limit)).offset(max(offset, 0))).scalars().all()
    return _page_response([dump_document(document) for document in documents], total, limit, offset)


@app.get("/api/admin/overview")
def admin_overview(session: Session = Depends(get_session)) -> dict:
    source_statuses = dict(session.execute(select(Source.status, func.count(Source.id)).group_by(Source.status)).all())
    document_types = {
        f"{doc_type}/{status}": count
        for doc_type, status, count in session.execute(
            select(Document.document_type, Document.crawl_status, func.count(Document.id)).group_by(
                Document.document_type, Document.crawl_status
            )
        ).all()
    }
    totals = {
        "sources": session.scalar(select(func.count(Source.id))) or 0,
        "documents": session.scalar(select(func.count(Document.id))) or 0,
        "essay_documents": session.scalar(select(func.count(Document.id)).where(Document.document_type == DocumentType.ESSAY.value)) or 0,
        "links": session.scalar(select(func.count(Link.id))) or 0,
        "resolved_links": session.scalar(select(func.count(Link.id)).where(Link.target_document_id.is_not(None))) or 0,
        "crawl_jobs": session.scalar(select(func.count(CrawlJob.id))) or 0,
        "index_runs": session.scalar(select(func.count(IndexRun.id))) or 0,
    }
    return {
        "totals": totals,
        "source_statuses": source_statuses,
        "document_types": document_types,
    }


@app.get("/api/admin/sources")
def admin_sources(
    status: str | None = None,
    q: str | None = None,
    limit: int = 200,
    offset: int = 0,
    session: Session = Depends(get_session),
) -> dict:
    latest_job_started = (
        select(CrawlJob.source_id, func.max(CrawlJob.started_at).label("started_at"))
        .group_by(CrawlJob.source_id)
        .subquery()
    )
    latest_job = (
        select(CrawlJob)
        .join(
            latest_job_started,
            (CrawlJob.source_id == latest_job_started.c.source_id)
            & (CrawlJob.started_at == latest_job_started.c.started_at),
        )
        .subquery()
    )
    doc_counts = (
        select(
            Document.source_id,
            func.count(Document.id).label("document_count"),
            func.count(Document.id).filter(Document.document_type == DocumentType.ESSAY.value).label("essay_count"),
        )
        .group_by(Document.source_id)
        .subquery()
    )
    statement = (
        select(
            Source,
            latest_job.c.id,
            latest_job.c.index_run_id,
            func.coalesce(doc_counts.c.document_count, 0),
            func.coalesce(doc_counts.c.essay_count, 0),
            latest_job.c.status,
            latest_job.c.pages_fetched,
            latest_job.c.pages_failed,
            latest_job.c.documents_indexed,
            latest_job.c.links_seen,
            latest_job.c.sources_discovered,
            latest_job.c.started_at,
            latest_job.c.finished_at,
            latest_job.c.error,
        )
        .outerjoin(doc_counts, doc_counts.c.source_id == Source.id)
        .outerjoin(latest_job, latest_job.c.source_id == Source.id)
        .order_by(Source.last_checked_at.desc().nullslast(), Source.first_seen_at.desc())
    )
    if status:
        statement = statement.where(Source.status == status)
    if q:
        statement = statement.where(Source.canonical_domain.ilike(f"%{q}%"))
    total = _count_statement(session, statement)
    rows = session.execute(statement.limit(_clamped_limit(limit)).offset(max(offset, 0))).all()
    job_ids = [job_id for _source, job_id, *_rest in rows if job_id]
    finished_events_by_job = _finished_events_by_job(session, job_ids)
    runs_by_id = _runs_by_id(session, [index_run_id for _source, _job_id, index_run_id, *_rest in rows if index_run_id])
    items = [
        {
            "id": source.id,
            "canonical_domain": source.canonical_domain,
            "url": source.url,
            "status": source.status,
            "description": source.description,
            "rss_url": source.rss_url,
            "sitemap_url": source.sitemap_url,
            "first_seen_at": source.first_seen_at,
            "last_checked_at": source.last_checked_at,
            "document_count": int(document_count or 0),
            "essay_count": int(essay_count or 0),
            "latest_job": {
                "id": job_id,
                "index_run_id": index_run_id,
                "status": job_status,
                "pages_fetched": pages_fetched,
                "pages_failed": pages_failed,
                "documents_indexed": documents_indexed,
                "links_seen": links_seen,
                "sources_discovered": sources_discovered,
                "started_at": job_started_at,
                "finished_at": job_finished_at,
                "error": job_error,
                "outcome": _job_outcome(
                    job_status,
                    pages_fetched or 0,
                    documents_indexed or 0,
                    job_error,
                    finished_events_by_job.get(job_id, {}),
                    runs_by_id.get(index_run_id),
                ),
            }
            if job_status
            else None,
        }
        for (
            source,
            job_id,
            index_run_id,
            document_count,
            essay_count,
            job_status,
            pages_fetched,
            pages_failed,
            documents_indexed,
            links_seen,
            sources_discovered,
            job_started_at,
            job_finished_at,
            job_error,
        ) in rows
    ]
    return _page_response(items, total, limit, offset)


@app.get("/api/admin/crawl-jobs")
def admin_crawl_jobs(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    source_id: int | None = None,
    index_run_id: int | None = None,
    session: Session = Depends(get_session),
) -> dict:
    statement = select(CrawlJob, Source).join(Source, CrawlJob.source_id == Source.id).order_by(desc(CrawlJob.started_at))
    if status and status != "all":
        statement = statement.where(CrawlJob.status == status)
    if source_id:
        statement = statement.where(CrawlJob.source_id == source_id)
    if index_run_id:
        statement = statement.where(CrawlJob.index_run_id == index_run_id)
    total = _count_statement(session, statement)
    rows = session.execute(statement.limit(_clamped_limit(limit)).offset(max(offset, 0))).all()
    finished_events_by_job = _finished_events_by_job(session, [job.id for job, _source in rows])
    runs_by_id = _runs_by_id(session, [job.index_run_id for job, _source in rows if job.index_run_id])
    items = [
        {
            "id": job.id,
            "source_id": job.source_id,
            "source_domain": source.canonical_domain,
            "index_run_id": job.index_run_id,
            "status": job.status,
            "pages_fetched": job.pages_fetched,
            "pages_failed": job.pages_failed,
            "documents_indexed": job.documents_indexed,
            "links_seen": job.links_seen,
            "sources_discovered": job.sources_discovered,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "error": job.error,
            "outcome": _job_outcome(
                job.status,
                job.pages_fetched,
                job.documents_indexed,
                job.error,
                finished_events_by_job.get(job.id, {}),
                runs_by_id.get(job.index_run_id),
            ),
        }
        for job, source in rows
    ]
    return _page_response(items, total, limit, offset)


def _clamped_limit(limit: int) -> int:
    return max(1, min(limit, 250))


def _count_statement(session: Session, statement) -> int:
    return session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0


def _page_response(items: list, total: int, limit: int, offset: int) -> dict:
    page_limit = _clamped_limit(limit)
    page_offset = max(offset, 0)
    return {
        "items": items,
        "total": total,
        "limit": page_limit,
        "offset": page_offset,
        "has_next": page_offset + page_limit < total,
        "has_previous": page_offset > 0,
    }


def _finished_events_by_job(session: Session, job_ids: list[int]) -> dict[int, dict]:
    if not job_ids:
        return {}
    events = session.execute(
        select(IndexEvent)
        .where(IndexEvent.crawl_job_id.in_(job_ids))
        .where(IndexEvent.event_type == IndexEventType.SOURCE_FINISHED.value)
    ).scalars().all()
    parsed: dict[int, dict] = {}
    for event in events:
        if not event.crawl_job_id or not event.payload:
            continue
        try:
            parsed[event.crawl_job_id] = json.loads(event.payload)
        except json.JSONDecodeError:
            parsed[event.crawl_job_id] = {}
    return parsed


def _runs_by_id(session: Session, run_ids: list[int]) -> dict[int, IndexRun]:
    filtered = [run_id for run_id in run_ids if run_id]
    if not filtered:
        return {}
    runs = session.execute(select(IndexRun).where(IndexRun.id.in_(filtered))).scalars().all()
    return {run.id: run for run in runs}


def _job_outcome(
    status: str,
    pages_fetched: int,
    documents_indexed: int,
    error: str | None,
    event_payload: dict,
    run: IndexRun | None,
) -> str:
    if status == CrawlJobStatus.SKIPPED.value:
        return "rejected by source classifier"
    if status == CrawlJobStatus.FAILED.value:
        return (error or "crawl failed").splitlines()[0]
    if status == CrawlJobStatus.RUNNING.value:
        return "currently crawling"
    if status != CrawlJobStatus.SUCCEEDED.value:
        return status
    max_documents = event_payload.get("max_documents_per_source")
    if max_documents and documents_indexed >= int(max_documents):
        return f"stopped after document limit ({max_documents})"
    max_pages = run.max_pages if run else None
    if max_pages and pages_fetched >= max_pages:
        return f"stopped after page limit ({max_pages})"
    return "finished: exhausted discovered candidates / link queue"


@app.get("/api/admin/index-runs")
def admin_index_runs(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    session: Session = Depends(get_session),
) -> dict:
    statement = select(IndexRun).order_by(desc(IndexRun.started_at))
    if status and status != "all":
        statement = statement.where(IndexRun.status == status)
    total = _count_statement(session, statement)
    runs = session.execute(statement.limit(_clamped_limit(limit)).offset(max(offset, 0))).scalars().all()
    items = [
        {
            "id": run.id,
            "status": run.status,
            "mode": run.mode,
            "dry_run": bool(run.dry_run),
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "budget_sources": run.budget_sources,
            "max_pages": run.max_pages,
            "max_depth": run.max_depth,
            "planned_sources": run.planned_sources,
            "attempted_sources": run.attempted_sources,
            "crawled_sources": run.crawled_sources,
            "ignored_sources": run.ignored_sources,
            "documents_indexed": run.documents_indexed,
            "links_seen": run.links_seen,
            "sources_discovered": run.sources_discovered,
            "errors": run.errors,
            "stop_reason": run.stop_reason,
        }
        for run in runs
    ]
    return _page_response(items, total, limit, offset)


@app.get("/api/documents/{document_id}")
def get_document(document_id: int, session: Session = Depends(get_session)) -> dict:
    document = session.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    outgoing = session.execute(select(Link).where(Link.source_document_id == document_id)).scalars().all()
    incoming = session.execute(select(Link).where(Link.target_document_id == document_id)).scalars().all()
    payload = dump_document(document).model_dump()
    payload["extracted_text"] = document.extracted_text
    payload["outgoing_links"] = [
        {
            "target_url": link.target_url,
            "target_domain": link.target_domain,
            "target_document_id": link.target_document_id,
            "anchor_text": link.anchor_text,
            "context": link.context,
        }
        for link in outgoing
    ]
    payload["incoming_links"] = [
        {
            "source_document_id": link.source_document_id,
            "target_url": link.target_url,
            "anchor_text": link.anchor_text,
        }
        for link in incoming
    ]
    return payload


@app.get("/api/search", response_model=SearchSchema)
def search(q: str, limit: int = 12, session: Session = Depends(get_session)) -> SearchSchema:
    search_row, ranked = search_documents(session, q, limit=limit, persist=True)
    answer = search_row.answer if search_row else synthesize_answer(q, ranked)
    return SearchSchema(
        search_id=search_row.id if search_row else None,
        query=q,
        answer=answer or "",
        results=[
            {
                "document": dump_document(item.document),
                "score": item.score,
                "reason": item.reason,
            }
            for item in ranked
        ],
    )


@app.get("/api/digest", response_model=list[DigestItemSchema])
def digest(limit: int = 20, session: Session = Depends(get_session)) -> list[DigestItemSchema]:
    items = get_digest(session, limit=limit)
    return [dump_digest_item(item) for item in items]


@app.post("/api/digest/populate", response_model=list[DigestItemSchema])
def populate_digest_endpoint(limit: int = 30, session: Session = Depends(get_session)) -> list[DigestItemSchema]:
    items = populate_digest(session, limit=limit)
    return [dump_digest_item(item) for item in items]


@app.post("/api/feedback")
def feedback(payload: FeedbackSchema, session: Session = Depends(get_session)) -> dict:
    record_feedback(
        session,
        document_id=payload.document_id,
        surface=payload.surface,
        action=payload.action,
        search_id=payload.search_id,
        digest_item_id=payload.digest_item_id,
    )
    return {"ok": True}


@app.get("/api/graph", response_model=GraphSchema)
def graph(document_id: int | None = None, session: Session = Depends(get_session)) -> GraphSchema:
    if document_id:
        document_ids = {document_id}
        links = session.execute(
            select(Link).where((Link.source_document_id == document_id) | (Link.target_document_id == document_id))
        ).scalars().all()
        for link in links:
            document_ids.add(link.source_document_id)
            if link.target_document_id:
                document_ids.add(link.target_document_id)
    else:
        links = session.execute(select(Link).where(Link.target_document_id.is_not(None)).limit(120)).scalars().all()
        document_ids = {link.source_document_id for link in links}
        document_ids.update(link.target_document_id for link in links if link.target_document_id)
    documents = session.execute(
        select(Document).options(joinedload(Document.source)).where(Document.id.in_(document_ids))
    ).scalars().all()
    nodes = [
        {
            "id": f"doc:{document.id}",
            "label": document.title or document.source.canonical_domain,
            "type": document.document_type,
            "domain": document.source.canonical_domain,
        }
        for document in documents
    ]
    edges = [
        {
            "source": f"doc:{link.source_document_id}",
            "target": f"doc:{link.target_document_id}",
            "label": link.anchor_text,
        }
        for link in links
        if link.target_document_id
    ]
    return GraphSchema(nodes=nodes, edges=edges)
