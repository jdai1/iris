"""Persistence helpers for extracted link rows."""

from __future__ import annotations

from sqlalchemy import select

from iris.dao import db
from iris.models import Document, Link, Source
from iris.schemas.enums import LinkType
from iris.services.common.url_utils import domain_for_url, is_valid_http_url, normalize_url


def upsert_link(
    *,
    source_document: Document,
    target_url: str,
    anchor_text: str | None,
    context: str | None,
) -> Link:
    """Insert or update a link emitted by a source document."""
    session = db.current_session()
    normalized = normalize_url(target_url)
    if not is_valid_http_url(normalized):
        raise ValueError(f"invalid link URL: {target_url[:120]}")
    target_domain = domain_for_url(normalized)
    target_source = session.execute(select(Source).where(Source.canonical_domain == target_domain)).scalar_one_or_none()
    target_document = session.execute(select(Document).where(Document.url == normalized)).scalar_one_or_none()
    link = session.execute(
        select(Link).where(
            Link.source_document_id == source_document.id,
            Link.target_url == normalized,
        )
    ).scalar_one_or_none()
    if link is None:
        link = Link(source_document_id=source_document.id, target_url=normalized)
        session.add(link)
    link.target_domain = target_domain
    link.target_source_id = target_source.id if target_source else None
    link.target_document_id = target_document.id if target_document else None
    link.anchor_text = anchor_text
    link.context = context
    link.link_type = LinkType.INTERNAL.value if target_domain == source_document.source.canonical_domain else LinkType.EXTERNAL.value
    session.flush()
    return link
