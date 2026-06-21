"""Persistence helpers for corpus search."""

from __future__ import annotations

from sqlalchemy import inspect, select, text

from iris.dao import db
from iris.dao.user_state import get_or_create_local_user
from iris.models import Document, Link, UserDocumentMapping
from iris.schemas.enums import CrawlStatus, DocumentType


def get_searchable_documents() -> list[Document]:
    """Return fetched essay documents eligible for search ranking."""
    session = db.current_session()
    return (
        session.execute(
            select(Document)
            .where(Document.document_type == DocumentType.ESSAY.value)
            .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        )
        .scalars()
        .all()
    )


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


def vector_search_documents(query_vector: list[float], *, limit: int) -> list[tuple[Document, float]]:
    """Return nearest documents using pgvector when the optional mirror column exists."""
    session = db.current_session()
    if session.bind is None or session.bind.dialect.name != "postgresql":
        return []
    columns = {column["name"] for column in inspect(session.connection()).get_columns("documents")}
    if "embedding_vector" not in columns:
        return []
    vector_literal = "[" + ",".join(f"{value:.8f}" for value in query_vector) + "]"
    rows = session.execute(
        text(
            "select id, 1 - (embedding_vector <=> cast(:query_vector as vector)) as similarity "
            "from documents "
            "where document_type = :document_type "
            "and crawl_status = :crawl_status "
            "and embedding_vector is not null "
            "order by embedding_vector <=> cast(:query_vector as vector) "
            "limit :limit"
        ),
        {
            "query_vector": vector_literal,
            "document_type": DocumentType.ESSAY.value,
            "crawl_status": CrawlStatus.FETCHED.value,
            "limit": max(1, min(limit, 500)),
        },
    ).all()

    document_ids = [int(row.id) for row in rows]
    if not document_ids:
        return []
    documents = session.execute(select(Document).where(Document.id.in_(document_ids))).scalars().all()
    by_id = {document.id: document for document in documents}
    return [(by_id[int(row.id)], float(row.similarity)) for row in rows if int(row.id) in by_id]
