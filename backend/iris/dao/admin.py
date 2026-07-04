"""Read helpers for the admin API views."""

from __future__ import annotations

import json
from collections import Counter
from collections import defaultdict

from sqlalchemy import desc, func, select
from sqlalchemy.orm import joinedload

from iris.dao import db
from iris.dao import search as search_dao
from iris.models import CrawlJob, Document, IndexEvent, IndexRun, Link, Source
from iris.schemas.api import (
    AdminCrawlJobSchema,
    AdminIndexRunSchema,
    AdminLatestJobSchema,
    AdminOverviewSchema,
    AdminSourceSchema,
    DocumentSchema,
    EmbeddingNeighborSchema,
    EmbeddingMapPointSchema,
    EmbeddingMapSchema,
    HealthCountsSchema,
)
from iris.schemas.enums import CrawlJobStatus, DocumentType, IndexEventType
from iris.schemas.enums import SourceStatus
from iris.schemas.indexing import SourceFinishedEventPayload
from iris.services.ingestion.embedding import cosine, loads_embedding
from iris.services.retrieval.embedding_map import EmbeddingProjection, project_embeddings


_embedding_projection_cache: dict[tuple[int, tuple[tuple[int, str | None], ...]], EmbeddingProjection] = {}


def get_health_counts() -> HealthCountsSchema:
    """Return high-level source and document counts."""
    session = db.current_session()
    return HealthCountsSchema(
        sources=session.scalar(select(func.count(Source.id))) or 0,
        documents=session.scalar(select(func.count(Document.id))) or 0,
    )


def get_sources(*, status: str | None = None, limit: int = 200) -> list[Source]:
    """Return a bounded source list newest-first."""
    session = db.current_session()
    statement = select(Source).order_by(Source.first_seen_at.desc())
    if status and status != "all":
        statement = statement.where(Source.status == status)
    return session.execute(statement.limit(clamped_limit(limit))).scalars().all()


def get_source(source_id: int) -> Source | None:
    """Fetch a source by id."""
    return db.current_session().get(Source, source_id)


def get_documents_page(
    *,
    limit: int,
    offset: int,
    source_id: int | None = None,
    document_type: str | None = None,
    crawl_job_id: int | None = None,
    index_run_id: int | None = None,
) -> tuple[list[Document], int]:
    """Return a filtered page of documents and total count."""
    session = db.current_session()
    statement = select(Document).options(joinedload(Document.source)).order_by(Document.last_crawled_at.desc())
    if source_id:
        statement = statement.where(Document.source_id == source_id)
    if document_type and document_type != "all":
        statement = statement.where(Document.document_type == document_type)
    if crawl_job_id:
        job = session.get(CrawlJob, crawl_job_id)
        if not job:
            return [], 0
        statement = statement.where(Document.crawl_job_id == job.id)
    if index_run_id:
        job_ids = list(session.scalars(select(CrawlJob.id).where(CrawlJob.index_run_id == index_run_id)))
        if not job_ids:
            return [], 0
        statement = statement.where(Document.crawl_job_id.in_(job_ids))
    total = count_statement(statement)
    documents = session.execute(statement.limit(clamped_limit(limit)).offset(max(offset, 0))).scalars().all()
    return documents, total


def get_admin_overview() -> AdminOverviewSchema:
    """Return aggregate counts for the admin overview."""
    session = db.current_session()
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
    return AdminOverviewSchema(totals=totals, source_statuses=source_statuses, document_types=document_types)


def get_embedding_map(*, limit: int) -> EmbeddingMapSchema:
    """Return embedded essay documents projected into a compact 3D map."""
    session = db.current_session()
    statement = (
        select(Document)
        .options(joinedload(Document.source))
        .where(Document.embedding_vector.is_not(None))
        .where(Document.document_type == DocumentType.ESSAY.value)
        .order_by(Document.id.asc())
    )
    documents = session.execute(statement.limit(clamped_embedding_limit(limit))).scalars().all()

    loaded: list[tuple[Document, list[float]]] = []
    for document in documents:
        try:
            vector = loads_embedding(document.embedding_vector)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if any(value != 0.0 for value in vector):
            loaded.append((document, vector))

    dimension_counts = Counter(len(vector) for _, vector in loaded)
    dimensions = dimension_counts.most_common(1)[0][0] if dimension_counts else 0
    projected_documents = [document for document, vector in loaded if len(vector) == dimensions]
    vectors = [vector for _, vector in loaded if len(vector) == dimensions]
    cache_key = (dimensions, tuple((document.id, document.content_hash) for document in projected_documents))
    projection = _embedding_projection_cache.get(cache_key)
    if projection is None:
        projection = project_embeddings(vectors)
        _embedding_projection_cache.clear()
        _embedding_projection_cache[cache_key] = projection
    return EmbeddingMapSchema(
        points=[
            EmbeddingMapPointSchema(
                document=_embedding_map_document(document),
                x=point.x,
                y=point.y,
                z=point.z,
                cluster_id=point.cluster_id,
            )
            for document, point in zip(projected_documents, projection.points)
        ],
        total_embedded=len(projected_documents),
        dimensions=dimensions,
        projection_method=projection.method,
    )


def get_embedding_neighbors(document_id: int, *, limit: int = 5) -> list[EmbeddingNeighborSchema] | None:
    """Return nearest essay documents by full-dimensional embedding cosine similarity."""
    session = db.current_session()
    selected = session.get(Document, document_id)
    if not selected or not selected.embedding_vector:
        return None
    try:
        selected_vector = loads_embedding(selected.embedding_vector)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    vector_rows = search_dao.vector_search_documents(selected_vector, limit=limit, exclude_document_id=document_id)
    if vector_rows:
        return [
            EmbeddingNeighborSchema(
                document=_embedding_map_document(document),
                similarity=round(score, 4),
            )
            for document, score in vector_rows[: max(1, min(limit, 20))]
        ]

    statement = (
        select(Document)
        .options(joinedload(Document.source))
        .where(Document.id != document_id)
        .where(Document.embedding_vector.is_not(None))
        .where(Document.document_type == DocumentType.ESSAY.value)
    )
    documents = session.execute(statement.limit(2000)).scalars().all()
    neighbors: list[EmbeddingNeighborSchema] = []
    for document in documents:
        try:
            vector = loads_embedding(document.embedding_vector)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        score = cosine(selected_vector, vector)
        neighbors.append(
            EmbeddingNeighborSchema(
                document=_embedding_map_document(document),
                similarity=round(score, 4),
            )
        )
    neighbors.sort(key=lambda item: item.similarity, reverse=True)
    return neighbors[: max(1, min(limit, 20))]


def get_admin_sources_page(*, status: str | None, q: str | None, limit: int, offset: int) -> tuple[list[AdminSourceSchema], int]:
    """Return a page of source rows with latest crawl job context."""
    session = db.current_session()
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
    total = count_statement(statement)
    rows = session.execute(statement.limit(clamped_limit(limit)).offset(max(offset, 0))).all()
    job_ids = [job_id for _source, job_id, *_rest in rows if job_id]
    finished_events_by_job = finished_events_by_job_id(job_ids)
    runs_by_id = index_runs_by_id([index_run_id for _source, _job_id, index_run_id, *_rest in rows if index_run_id])
    items: list[AdminSourceSchema] = []
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
    ) in rows:
        items.append(
            AdminSourceSchema(
                id=source.id,
                canonical_domain=source.canonical_domain,
                url=source.url,
                status=source.status,
                description=source.description,
                rss_url=source.rss_url,
                sitemap_url=source.sitemap_url,
                first_seen_at=source.first_seen_at,
                last_checked_at=source.last_checked_at,
                document_count=int(document_count or 0),
                essay_count=int(essay_count or 0),
                latest_job=AdminLatestJobSchema(
                    id=job_id,
                    index_run_id=index_run_id,
                    status=job_status,
                    pages_fetched=pages_fetched,
                    pages_failed=pages_failed,
                    documents_indexed=documents_indexed,
                    links_seen=links_seen,
                    sources_discovered=sources_discovered,
                    started_at=job_started_at,
                    finished_at=job_finished_at,
                    error=job_error,
                    outcome=get_job_outcome(
                        job_status,
                        pages_fetched or 0,
                        documents_indexed or 0,
                        job_error,
                        finished_events_by_job.get(job_id, SourceFinishedEventPayload()),
                        runs_by_id.get(index_run_id),
                    ),
                )
                if job_status
                else None,
            )
        )
    return items, total


def search_graph_sources(q: str, *, limit: int = 20) -> list[AdminSourceSchema]:
    """Search all indexed source nodes for graph focusing."""
    session = db.current_session()
    normalized = q.strip().lower()
    if not normalized:
        return []
    pattern = f"%{normalized}%"
    rows = session.execute(
        select(Source, func.count(Document.id).label("document_count"))
        .outerjoin(Document, Document.source_id == Source.id)
        .where(Source.status == SourceStatus.INDEXED.value)
        .where(
            Source.canonical_domain.ilike(pattern)
            | Source.name.ilike(pattern)
            | Source.description.ilike(pattern)
        )
        .group_by(Source.id)
        .order_by(desc(func.count(Document.id)), Source.canonical_domain)
        .limit(max(1, min(limit, 50)))
    ).all()
    return [
        AdminSourceSchema(
            id=source.id,
            canonical_domain=source.canonical_domain,
            name=source.name,
            status=source.status,
            url=source.url,
            rss_url=source.rss_url,
            sitemap_url=source.sitemap_url,
            description=source.description,
            first_seen_at=source.first_seen_at,
            last_checked_at=source.last_checked_at,
            document_count=int(document_count or 0),
            essay_count=int(document_count or 0),
            latest_job=None,
        )
        for source, document_count in rows
    ]


def get_admin_crawl_jobs_page(
    *,
    limit: int,
    offset: int,
    status: CrawlJobStatus | None,
    source_id: int | None,
    index_run_id: int | None,
) -> tuple[list[AdminCrawlJobSchema], int]:
    """Return a page of crawl jobs with source and outcome context."""
    session = db.current_session()
    statement = select(CrawlJob, Source).join(Source, CrawlJob.source_id == Source.id).order_by(desc(CrawlJob.started_at))
    if status:
        statement = statement.where(CrawlJob.status == status.value)
    if source_id:
        statement = statement.where(CrawlJob.source_id == source_id)
    if index_run_id:
        statement = statement.where(CrawlJob.index_run_id == index_run_id)
    total = count_statement(statement)
    rows = session.execute(statement.limit(clamped_limit(limit)).offset(max(offset, 0))).all()
    finished_events_by_job = finished_events_by_job_id([job.id for job, _source in rows])
    runs_by_id = index_runs_by_id([job.index_run_id for job, _source in rows if job.index_run_id])
    items: list[AdminCrawlJobSchema] = []
    for job, source in rows:
        items.append(
            AdminCrawlJobSchema(
                id=job.id,
                source_id=job.source_id,
                source_domain=source.canonical_domain,
                index_run_id=job.index_run_id,
                status=job.status,
                pages_fetched=job.pages_fetched,
                pages_failed=job.pages_failed,
                documents_indexed=job.documents_indexed,
                current_document_count=_count_documents_for_job(job),
                links_seen=job.links_seen,
                sources_discovered=job.sources_discovered,
                started_at=job.started_at,
                finished_at=job.finished_at,
                error=job.error,
                outcome=get_job_outcome(
                    job.status,
                    job.pages_fetched,
                    job.documents_indexed,
                    job.error,
                    finished_events_by_job.get(job.id, SourceFinishedEventPayload()),
                    runs_by_id.get(job.index_run_id),
                ),
            )
        )
    return items, total


def get_admin_index_runs_page(*, limit: int, offset: int, status: str | None) -> tuple[list[AdminIndexRunSchema], int]:
    """Return a page of index runs for the admin UI."""
    session = db.current_session()
    statement = select(IndexRun).order_by(desc(IndexRun.started_at))
    if status and status != "all":
        statement = statement.where(IndexRun.status == status)
    total = count_statement(statement)
    runs = session.execute(statement.limit(clamped_limit(limit)).offset(max(offset, 0))).scalars().all()
    return [
        AdminIndexRunSchema(
            id=run.id,
            status=run.status,
            mode=run.mode,
            dry_run=bool(run.dry_run),
            started_at=run.started_at,
            finished_at=run.finished_at,
            budget_sources=run.budget_sources,
            max_pages=run.max_pages,
            max_depth=run.max_depth,
            planned_sources=run.planned_sources,
            attempted_sources=run.attempted_sources,
            crawled_sources=run.crawled_sources,
            ignored_sources=run.ignored_sources,
            documents_indexed=run.documents_indexed,
            current_document_count=_count_documents_for_run(run.id),
            links_seen=run.links_seen,
            sources_discovered=run.sources_discovered,
            errors=run.errors,
            stop_reason=run.stop_reason,
        )
        for run in runs
    ], total


def get_document_detail(document_id: int) -> tuple[Document | None, list[Link], list[Link]]:
    """Return a document plus outgoing and incoming links."""
    session = db.current_session()
    document = session.get(Document, document_id)
    if not document:
        return None, [], []
    outgoing = session.execute(select(Link).where(Link.source_document_id == document_id)).scalars().all()
    incoming = session.execute(select(Link).where(Link.target_document_id == document_id)).scalars().all()
    return document, outgoing, incoming


def get_graph_rows(document_id: int | None = None, *, limit: int = 120) -> tuple[list[Document], list[Link]]:
    """Return graph documents and links for one document or a default sample."""
    session = db.current_session()
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
        links = session.execute(
            select(Link)
            .join(Document, Link.source_document_id == Document.id)
            .where(Link.target_document_id.is_not(None))
            .where(Document.document_type == DocumentType.ESSAY.value)
            .limit(max(1, min(limit, 500)))
        ).scalars().all()
        document_ids = {link.source_document_id for link in links}
        document_ids.update(link.target_document_id for link in links if link.target_document_id)
    documents = session.execute(
        select(Document).options(joinedload(Document.source)).where(Document.id.in_(document_ids))
    ).scalars().all()
    return documents, links


def get_source_graph_rows(
    *,
    source_id: int | None = None,
    domain: str | None = None,
    limit: int = 120,
    depth: int = 1,
) -> tuple[list[Source], list[tuple[int, int, int]]]:
    """Return source nodes and weighted source-to-source link edges."""
    session = db.current_session()
    seed_id = source_id
    if domain and not seed_id:
        seed = session.scalar(select(Source).where(Source.canonical_domain == domain))
        seed_id = seed.id if seed else None

    base_edge_statement = (
        select(Document.source_id, Link.target_source_id, func.count(Link.id).label("weight"))
        .join(Link, Link.source_document_id == Document.id)
        .where(Link.target_source_id.is_not(None))
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == "fetched")
        .where(Document.source_id != Link.target_source_id)
        .where(Document.source_id.in_(select(Source.id).where(Source.status == SourceStatus.INDEXED.value)))
        .where(Link.target_source_id.in_(select(Source.id).where(Source.status == SourceStatus.INDEXED.value)))
        .group_by(Document.source_id, Link.target_source_id)
        .order_by(desc(func.count(Link.id)))
    )
    if seed_id:
        selected_ids = {int(seed_id)}
        frontier = {int(seed_id)}
        rows_by_pair: dict[tuple[int, int], int] = {}
        graph_depth = max(1, min(depth, 3))
        for _ in range(graph_depth):
            layer_rows = session.execute(
                base_edge_statement
                .where((Document.source_id.in_(frontier)) | (Link.target_source_id.in_(frontier)))
                .limit(max(1, min(limit, 500)))
            ).all()
            next_frontier: set[int] = set()
            for source, target, _weight in layer_rows:
                source_id = int(source)
                target_id = int(target)
                rows_by_pair[(source_id, target_id)] = int(_weight or 1)
                next_frontier.add(source_id)
                next_frontier.add(target_id)
            next_frontier -= selected_ids
            selected_ids.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        rows = [(source, target, weight) for (source, target), weight in rows_by_pair.items()]
    else:
        rows = session.execute(base_edge_statement.limit(max(1, min(limit, 500)))).all()
    if not rows and seed_id:
        source = session.get(Source, seed_id)
        return ([source] if source else []), []

    node_scores: dict[int, int] = defaultdict(int)
    for source, target, weight in rows:
        node_scores[int(source)] += int(weight or 0)
        node_scores[int(target)] += int(weight or 0)
    node_ids = list(node_scores.keys())
    sources = session.execute(select(Source).where(Source.id.in_(node_ids))).scalars().all() if node_ids else []
    sources.sort(key=lambda source: node_scores.get(source.id, 0), reverse=True)
    return sources, [(int(source), int(target), int(weight or 1)) for source, target, weight in rows]


def _count_documents_for_job(job: CrawlJob) -> int:
    session = db.current_session()
    return session.scalar(select(func.count(Document.id)).where(Document.crawl_job_id == job.id)) or 0


def _count_documents_for_run(run_id: int) -> int:
    session = db.current_session()
    job_ids = list(session.scalars(select(CrawlJob.id).where(CrawlJob.index_run_id == run_id)))
    if not job_ids:
        return 0
    return session.scalar(select(func.count(Document.id)).where(Document.crawl_job_id.in_(job_ids))) or 0


def clamped_limit(limit: int) -> int:
    """Clamp API page size to the supported range."""
    return max(1, min(limit, 250))


def clamped_embedding_limit(limit: int) -> int:
    """Clamp embedding-map payloads separately from table pagination."""
    return max(1, min(limit, 5000))


def _embedding_map_document(document: Document) -> DocumentSchema:
    return DocumentSchema(
        id=document.id,
        source_id=document.source_id,
        source_domain=document.source.canonical_domain,
        url=document.url,
        document_type=document.document_type,
        category=document.category,
        title=document.title,
        author=document.author,
        published_at=document.published_at,
        summary=document.summary,
        topics=document.topics or [],
    )


def count_statement(statement) -> int:
    """Count rows produced by a SQLAlchemy statement."""
    session = db.current_session()
    return session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0


def finished_events_by_job_id(job_ids: list[int]) -> dict[int, SourceFinishedEventPayload]:
    """Return parsed source-finished event payloads keyed by crawl job id."""
    if not job_ids:
        return {}
    session = db.current_session()
    events = session.execute(
        select(IndexEvent)
        .where(IndexEvent.crawl_job_id.in_(job_ids))
        .where(IndexEvent.event_type == IndexEventType.SOURCE_FINISHED.value)
    ).scalars().all()
    parsed: dict[int, SourceFinishedEventPayload] = {}
    for event in events:
        if not event.crawl_job_id or not event.payload:
            continue
        try:
            payload = json.loads(event.payload)
        except json.JSONDecodeError:
            payload = {}
        parsed[event.crawl_job_id] = SourceFinishedEventPayload(
            max_documents_per_source=payload.get("max_documents_per_source") if isinstance(payload, dict) else None,
        )
    return parsed


def index_runs_by_id(run_ids: list[int]) -> dict[int, IndexRun]:
    """Fetch index runs keyed by id."""
    filtered = [run_id for run_id in run_ids if run_id]
    if not filtered:
        return {}
    session = db.current_session()
    runs = session.execute(select(IndexRun).where(IndexRun.id.in_(filtered))).scalars().all()
    return {run.id: run for run in runs}


def get_job_outcome(
    status: str,
    pages_fetched: int,
    documents_indexed: int,
    error: str | None,
    event_payload: SourceFinishedEventPayload,
    run: IndexRun | None,
) -> str:
    """Summarize why a crawl job stopped."""
    if status == CrawlJobStatus.SKIPPED.value:
        return "rejected by source classifier"
    if status == CrawlJobStatus.FAILED.value:
        return (error or "crawl failed").splitlines()[0]
    if status == CrawlJobStatus.RUNNING.value:
        return "currently crawling"
    if status != CrawlJobStatus.SUCCEEDED.value:
        return status
    max_documents = event_payload.max_documents_per_source
    if max_documents and documents_indexed >= int(max_documents):
        return f"stopped after document limit ({max_documents})"
    max_pages = run.max_pages if run else None
    if max_pages and pages_fetched >= max_pages:
        return f"stopped after page limit ({max_pages})"
    return "finished: exhausted discovered candidates / link queue"
