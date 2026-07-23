from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from iris.dao import db
from iris.models import DocumentHighlight, User, UserDocumentMapping


def list_for_mapping(mapping: UserDocumentMapping) -> list[DocumentHighlight]:
    return list(db.current_session().scalars(
        select(DocumentHighlight)
        .where(DocumentHighlight.user_document_mapping_id == mapping.id)
        .where(DocumentHighlight.deleted_at.is_(None))
        .order_by(DocumentHighlight.created_at, DocumentHighlight.id)
    ))


def create(mapping: UserDocumentMapping, **values) -> DocumentHighlight:
    quote = values["quote"].strip()
    if not quote:
        raise ValueError("Highlight quote cannot be empty")
    start, end = values.get("start_offset"), values.get("end_offset")
    if start is not None and end is not None and end <= start:
        raise ValueError("Highlight end_offset must be greater than start_offset")
    highlight = DocumentHighlight(
        user_document_mapping_id=mapping.id,
        **{**values, "quote": quote},
    )
    db.current_session().add(highlight)
    db.current_session().flush()
    return highlight


def get_owned(user: User, highlight_id: int) -> DocumentHighlight | None:
    return db.current_session().scalar(
        select(DocumentHighlight)
        .join(DocumentHighlight.user_document_mapping)
        .where(DocumentHighlight.id == highlight_id)
        .where(UserDocumentMapping.user_id == user.id)
        .where(DocumentHighlight.deleted_at.is_(None))
    )


def update(highlight: DocumentHighlight, *, fields: set[str], comment=None, color=None) -> DocumentHighlight:
    if "comment" in fields:
        highlight.comment = comment.strip() if comment and comment.strip() else None
    if "color" in fields and color:
        highlight.color = color
    highlight.updated_at = datetime.now(timezone.utc)
    db.current_session().flush()
    return highlight


def soft_delete(highlight: DocumentHighlight) -> None:
    now = datetime.now(timezone.utc)
    highlight.deleted_at = now
    highlight.updated_at = now
    db.current_session().flush()
