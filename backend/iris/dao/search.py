"""Persistence helpers for corpus search."""

from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import joinedload

from iris.dao import db
from iris.dao.user_state import get_or_create_local_user
from iris.models import Document, Link, UserDocumentMapping
from iris.schemas.enums import CrawlStatus, DocumentType
from iris.schemas.retrieval import RankedDocument


def get_searchable_documents() -> list[Document]:
    """Return fetched essay documents eligible for search ranking."""
    session = db.current_session()
    return (
        session.execute(
            select(Document)
            .where(Document.document_type == DocumentType.ESSAY.value)
            .where(Document.crawl_status == CrawlStatus.FETCHED.value)
            .where(Document.embedding_vector.is_not(None))
        )
        .scalars()
        .all()
    )


def search_documents_for_picker(query: str, *, limit: int = 8) -> list[RankedDocument]:
    """Fast SQL-backed document search for picker UIs that only need rows."""
    session = db.current_session()
    normalized = query.strip()
    if not normalized:
        return []
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        return _postgres_document_picker_search(normalized, limit=limit)
    return _portable_document_picker_search(normalized, limit=limit)


def _postgres_document_picker_search(query: str, *, limit: int) -> list[RankedDocument]:
    session = db.current_session()
    rows = session.execute(
        text(
            """
            with query as (
                select websearch_to_tsquery('simple', :query) as tsquery
            )
            select
                d.id,
                ts_rank_cd(
                    setweight(to_tsvector('simple', coalesce(d.title, '')), 'A') ||
                    setweight(to_tsvector('simple', coalesce(d.author, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(d.one_liner, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(d.audience, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(d.summary, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(d.takeaways::text, '')), 'B') ||
                    setweight(to_tsvector('simple', coalesce(d.extracted_text, '')), 'D'),
                    query.tsquery
                ) as rank
            from documents d, query
            where d.document_type = :document_type
              and d.crawl_status = :crawl_status
              and (
                setweight(to_tsvector('simple', coalesce(d.title, '')), 'A') ||
                setweight(to_tsvector('simple', coalesce(d.author, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(d.one_liner, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(d.audience, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(d.summary, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(d.takeaways::text, '')), 'B') ||
                setweight(to_tsvector('simple', coalesce(d.extracted_text, '')), 'D')
              ) @@ query.tsquery
            order by rank desc, d.published_at desc nulls last, d.id desc
            limit :limit
            """
        ),
        {
            "query": query,
            "document_type": DocumentType.ESSAY.value,
            "crawl_status": CrawlStatus.FETCHED.value,
            "limit": max(1, min(limit, 50)),
        },
    ).all()
    return _ranked_documents_from_id_scores([(int(row.id), float(row.rank or 0.0)) for row in rows], reason="full-text match")


def _portable_document_picker_search(query: str, *, limit: int) -> list[RankedDocument]:
    session = db.current_session()
    terms = [term for term in query.lower().split() if term]
    pattern = f"%{query.lower()}%"
    statement = (
        select(Document)
        .options(joinedload(Document.source))
        .where(Document.document_type == DocumentType.ESSAY.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .where(
            text(
                "lower(coalesce(documents.title, '') || ' ' || "
                "coalesce(documents.author, '') || ' ' || "
                "coalesce(documents.one_liner, '') || ' ' || "
                "coalesce(documents.audience, '') || ' ' || "
                "coalesce(documents.summary, '') || ' ' || "
                "coalesce(documents.takeaways, '') || ' ' || "
                "coalesce(documents.extracted_text, '')) like :pattern"
            )
        )
        .order_by(Document.published_at.desc().nullslast(), Document.id.desc())
        .limit(max(1, min(limit * 4, 200)))
    )
    rows = session.execute(statement, {"pattern": pattern}).scalars().all()
    scored: list[RankedDocument] = []
    for document in rows:
        score = _picker_keyword_score(terms, document)
        if score > 0:
            scored.append(RankedDocument(document=document, score=score, reason="keyword match"))
    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[: max(1, min(limit, 50))]


def _ranked_documents_from_id_scores(id_scores: list[tuple[int, float]], *, reason: str) -> list[RankedDocument]:
    if not id_scores:
        return []
    session = db.current_session()
    document_ids = [document_id for document_id, _score in id_scores]
    documents = (
        session.execute(select(Document).options(joinedload(Document.source)).where(Document.id.in_(document_ids)))
        .scalars()
        .all()
    )
    by_id = {document.id: document for document in documents}
    by_score = dict(id_scores)
    return [
        RankedDocument(document=by_id[document_id], score=by_score[document_id], reason=reason)
        for document_id in document_ids
        if document_id in by_id
    ]


def _picker_keyword_score(terms: list[str], document: Document) -> float:
    title = (document.title or "").lower()
    one_liner = (document.one_liner or "").lower()
    audience = (document.audience or "").lower()
    summary = (document.summary or "").lower()
    takeaways = " ".join(document.takeaways or []).lower()
    source = document.source.canonical_domain.lower()
    text = (document.extracted_text or "").lower()
    score = 0.0
    for term in terms:
        if term in title:
            score += 4.0
        if term in source:
            score += 2.5
        if term in one_liner:
            score += 2.5
        if term in audience:
            score += 2.0
        if term in summary:
            score += 2.0
        if term in takeaways:
            score += 2.0
        if term in text:
            score += 0.5
    return score


def get_favorited_document_ids() -> set[int]:
    """Return document ids favorited by the local user."""
    session = db.current_session()
    user = get_or_create_local_user()
    return set(
        session.execute(
            select(UserDocumentMapping.document_id)
            .where(UserDocumentMapping.user_id == user.id)
            .where(UserDocumentMapping.favorited_at.is_not(None))
        )
        .scalars()
        .all()
    )


def get_dismissed_document_ids() -> set[int]:
    """Return document ids dismissed by the local user."""
    session = db.current_session()
    user = get_or_create_local_user()
    return set(
        session.execute(
            select(UserDocumentMapping.document_id)
            .where(UserDocumentMapping.user_id == user.id)
            .where(UserDocumentMapping.dismissed_at.is_not(None))
        )
        .scalars()
        .all()
    )


def get_outgoing_links(document: Document) -> list[Link]:
    """Return outgoing links for one document."""
    session = db.current_session()
    return session.execute(select(Link).where(Link.source_document_id == document.id)).scalars().all()


def get_document(document_id: int) -> Document | None:
    """Fetch a document by id."""
    return db.current_session().get(Document, document_id)


def vector_search_documents(query_vector: list[float], *, limit: int, exclude_document_id: int | None = None) -> list[tuple[Document, float]]:
    """Return nearest documents using pgvector."""
    session = db.current_session()
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return []
    vector_literal = "[" + ",".join(f"{value:.8f}" for value in query_vector) + "]"
    rows = session.execute(
        text(
            "select id, 1 - (embedding_vector <=> cast(:query_vector as vector)) as similarity "
            "from documents "
            "where document_type = :document_type "
            "and crawl_status = :crawl_status "
            "and embedding_vector is not null "
            "and (:exclude_document_id is null or id != :exclude_document_id) "
            "order by embedding_vector <=> cast(:query_vector as vector) "
            "limit :limit"
        ),
        {
            "query_vector": vector_literal,
            "document_type": DocumentType.ESSAY.value,
            "crawl_status": CrawlStatus.FETCHED.value,
            "limit": max(1, min(limit, 500)),
            "exclude_document_id": exclude_document_id,
        },
    ).all()

    document_ids = [int(row.id) for row in rows]
    if not document_ids:
        return []
    documents = session.execute(select(Document).options(joinedload(Document.source)).where(Document.id.in_(document_ids))).scalars().all()
    by_id = {document.id: document for document in documents}
    return [(by_id[int(row.id)], float(row.similarity)) for row in rows if int(row.id) in by_id]
