"""Persistence helpers for corpus search."""

from __future__ import annotations

from sqlalchemy import String, case, cast, func, literal, or_, select, text
from sqlalchemy.orm import joinedload

from iris.dao import db
from iris.dao.user_state import get_or_create_local_user
from iris.models import (
    Category,
    Document,
    DocumentCategoryAssignment,
    DocumentTag,
    Link,
    Source,
    Tag,
    UserDocumentMapping,
)
from iris.schemas.enums import CrawlStatus, DocumentType
from iris.schemas.retrieval import RankedDocument


def _searchable():
    return (
        Document.document_type == DocumentType.ESSAY.value,
        Document.crawl_status == CrawlStatus.FETCHED.value,
        Document.embedding_vector.is_not(None),
    )


def get_searchable_document(document_id: int) -> Document | None:
    return db.current_session().scalar(
        select(Document).where(Document.id == document_id, *_searchable())
    )


def _ranked_search(score, *, limit: int, reason: str) -> list[RankedDocument]:
    # Rank in SQL before materializing full documents (especially text/vectors).
    statement = (
        select(Document.id, score.label("score"))
        .join(Source, Source.id == Document.source_id)
        .where(*_searchable(), score > 0)
        .order_by(score.desc(), Document.id)
        .limit(max(1, min(limit, 30)))
    )
    rows = db.current_session().execute(statement).all()
    return _ranked_documents_from_id_scores(
        [(row.id, float(row.score)) for row in rows], reason=reason
    )


def keyword_search_documents(terms: set[str], *, limit: int) -> list[RankedDocument]:
    if not terms:
        return []
    fields = [
        Document.title,
        Document.author,
        Document.one_liner,
        Document.audience,
        Document.summary,
        cast(Document.takeaways, String),
        cast(Document.topics, String),
        cast(Document.category, String),
        func.substr(Document.extracted_text, 1, 3000),
        Source.name,
        Source.canonical_domain,
    ]
    score = sum(
        case(
            (
                or_(
                    *(
                        func.lower(func.coalesce(field, "")).contains(
                            term, autoescape=True
                        )
                        for field in fields
                    )
                ),
                1.0,
            ),
            else_=0.0,
        )
        for term in sorted(terms)
    ) / len(terms)
    return _ranked_search(score, limit=limit, reason="keyword overlap")


def tag_search_documents(terms: set[str], *, limit: int) -> list[RankedDocument]:
    if not terms:
        return []
    session = db.current_session()
    if session.get_bind().dialect.name == "postgresql":
        # JSON null is distinct from SQL NULL and cannot be expanded as an array.
        topics_json = case(
            (func.json_typeof(Document.topics) == "array", Document.topics),
            else_=cast(literal("[]"), Document.topics.type),
        )
        topics = func.json_array_elements_text(topics_json).table_valued("value").render_derived()
    else:
        topics = func.json_each(Document.topics).table_valued("value")
    overlap = sum(
        case(
            (
                select(literal(1))
                .select_from(topics)
                .where(func.lower(topics.c.value) == term)
                .correlate(Document)
                .exists(),
                1.0,
            ),
            else_=0.0,
        )
        for term in sorted(terms)
    )
    topic_score = case((overlap > 0, 0.28 + 0.12 * overlap / len(terms)), else_=0.0)
    tag_overlap = sum(
        case(
            (or_(func.lower(Tag.name) == term, func.lower(Tag.slug) == term), 1.0),
            else_=0.0,
        )
        for term in sorted(terms)
    )
    tag_score = func.coalesce(
        select(func.max(0.38 + 0.12 * tag_overlap / len(terms)))
        .select_from(DocumentTag)
        .join(Tag, Tag.id == DocumentTag.tag_id)
        .where(DocumentTag.document_id == Document.id, tag_overlap > 0)
        .correlate(Document)
        .scalar_subquery(),
        0.0,
    )
    score = case((tag_score > topic_score, tag_score), else_=topic_score)
    return _ranked_search(score, limit=limit, reason="tag/topic match")


def category_search_documents(terms: set[str], *, limit: int) -> list[RankedDocument]:
    if not terms:
        return []
    assigned = (
        select(literal(1))
        .select_from(DocumentCategoryAssignment)
        .join(Category, Category.id == DocumentCategoryAssignment.category_id)
        .where(
            DocumentCategoryAssignment.document_id == Document.id,
            or_(
                func.lower(Category.slug).in_(terms),
                func.lower(Category.name).in_(terms),
            ),
        )
        .correlate(Document)
        .exists()
    )
    score = case(
        (assigned, 0.48),
        (func.lower(cast(Document.category, String)).in_(terms), 0.42),
        else_=0.0,
    )
    return _ranked_search(score, limit=limit, reason="category match")


def semantic_search_documents(
    vector: list[float], *, limit: int
) -> list[RankedDocument]:
    limit = max(1, min(limit, 30))
    if db.current_session().get_bind().dialect.name == "postgresql":
        pairs = vector_search_documents(vector, limit=limit)
    else:
        # SQLite has no pgvector: stream only IDs/vectors and retain top-k scores.
        from heapq import nlargest

        from iris.services.ingestion.embedding import cosine, loads_embedding

        statement = (
            select(Document.id, Document.embedding_vector)
            .where(*_searchable())
            .execution_options(yield_per=100)
        )
        with db.current_session().execute(statement) as result:
            scores = nlargest(
                limit,
                (
                    (row.id, cosine(vector, loads_embedding(row.embedding_vector)))
                    for row in result
                ),
                key=lambda item: item[1],
            )
        return [
            row
            for row in _ranked_documents_from_id_scores(
                scores, reason="embedding cosine"
            )
            if row.score > 0.04
        ]
    return [
        RankedDocument(
            document=document, score=score, reason=f"pgvector cosine {score:.2f}"
        )
        for document, score in pairs
        if score > 0.04
    ]


def recent_source_documents(source_id: int, *, limit: int = 10) -> list[Document]:
    return list(
        db.current_session().scalars(
            select(Document)
            .where(Document.source_id == source_id)
            .order_by(
                func.coalesce(Document.published_at, Document.first_seen_at).desc(),
                Document.id.desc(),
            )
            .limit(limit)
        )
    )


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
