"""Persistence helpers for corpus search."""

from __future__ import annotations

from sqlalchemy import select

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
