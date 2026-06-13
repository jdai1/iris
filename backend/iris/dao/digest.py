"""Persistence helpers for computed digest recommendations."""

from __future__ import annotations

from sqlalchemy import func, select

from iris.dao import db
from iris.dao.user_state import get_or_create_local_user
from iris.models import Document, Link, UserDocumentMapping
from iris.schemas.enums import CrawlStatus, DocumentType


def get_liked_documents_for_interest() -> list[Document]:
    """Return documents favorited or read by the local user."""
    session = db.current_session()
    user = get_or_create_local_user()
    return (
        session.execute(
            select(Document)
            .join(UserDocumentMapping, UserDocumentMapping.document_id == Document.id)
            .where(UserDocumentMapping.user_id == user.id)
            .where(
                (UserDocumentMapping.favorited_at.is_not(None))
                | (UserDocumentMapping.read_at.is_not(None))
                | (UserDocumentMapping.first_opened_at.is_not(None))
            )
        )
        .scalars()
        .all()
    )


def get_all_document_topics() -> list[list[str]]:
    """Return raw extracted topics for interest-vector fallback."""
    session = db.current_session()
    return list(session.execute(select(Document.topics).where(Document.topics.is_not(None))).scalars().all())


def get_dismissed_or_read_document_ids() -> set[int]:
    """Return local-user document ids that should not be recommended by default."""
    session = db.current_session()
    user = get_or_create_local_user()
    return set(
        session.execute(
            select(UserDocumentMapping.document_id)
            .where(UserDocumentMapping.user_id == user.id)
            .where((UserDocumentMapping.dismissed_at.is_not(None)) | (UserDocumentMapping.read_at.is_not(None)))
        )
        .scalars()
        .all()
    )


def get_digest_candidate_documents() -> list[Document]:
    """Return fetched essay documents eligible for digest ranking."""
    session = db.current_session()
    return (
        session.execute(
            select(Document).where(Document.document_type == DocumentType.ESSAY.value).where(Document.crawl_status == CrawlStatus.FETCHED.value)
        )
        .scalars()
        .all()
    )


def count_inbound_links(document: Document) -> int:
    """Return the number of resolved indexed links pointing at a document."""
    session = db.current_session()
    return session.execute(select(func.count(Link.id)).where(Link.target_document_id == document.id)).scalar_one()
