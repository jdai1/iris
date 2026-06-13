"""Backfills for derived local-user document state."""

from __future__ import annotations

from sqlalchemy import select

from iris.dao import db
from iris.dao.user_state import SYSTEM_NAMESPACE, classify_document_category, get_or_create_tag, tag_document
from iris.models import Document, DocumentCategory, DocumentTag, TagScope


def backfill_document_categories(limit: int | None = None) -> int:
    """Classify documents with an unknown category using local heuristics."""
    session = db.current_session()
    statement = select(Document).where(Document.category == DocumentCategory.UNKNOWN)
    if limit:
        statement = statement.limit(limit)
    documents = session.execute(statement).scalars().all()
    changed = 0
    for document in documents:
        category = classify_document_category(document)
        if category != document.category:
            document.category = category
            changed += 1
    session.flush()
    return changed


def backfill_system_tags_from_topics(limit: int | None = None) -> int:
    """Create system tags from existing document topic arrays."""
    session = db.current_session()
    statement = select(Document).where(Document.topics.is_not(None))
    if limit:
        statement = statement.limit(limit)
    documents = session.execute(statement).scalars().all()
    created_assignments = 0
    for document in documents:
        for topic in document.topics or []:
            if not topic or not topic.strip():
                continue
            tag = get_or_create_tag(topic, scope=TagScope.SYSTEM)
            before_id = session.execute(
                select(DocumentTag.id).where(
                    DocumentTag.document_id == document.id,
                    DocumentTag.tag_id == tag.id,
                    DocumentTag.assignment_namespace == SYSTEM_NAMESPACE,
                )
            ).scalar_one_or_none()
            tag_document(document, tag)
            if before_id is None:
                created_assignments += 1
    session.flush()
    return created_assignments
