from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from iris.models import Document, Link, LinkType, Source, SourceStatus
from iris.services.common.url_utils import domain_for_url, is_valid_http_url, normalize_url, root_url_for_domain


def get_or_create_source(
    session: Session,
    url: str,
    *,
    status: str = SourceStatus.QUEUED.value,
    discovered_from_source_id: int | None = None,
    force_status: bool = False,
) -> Source:
    normalized_url = normalize_url(url)
    root_url = root_url_for_domain(normalized_url)
    domain = domain_for_url(normalized_url)
    source = session.execute(select(Source).where(Source.canonical_domain == domain)).scalar_one_or_none()
    if source:
        if force_status:
            source.status = status
        elif source.status != SourceStatus.IGNORED.value and status == SourceStatus.IGNORED.value:
            source.status = status
        if source.url != root_url and source.discovered_from_source_id is not None:
            source.url = root_url
        return source
    source = Source(
        canonical_domain=domain,
        url=root_url,
        status=status,
        discovered_from_source_id=discovered_from_source_id,
    )
    session.add(source)
    session.flush()
    return source


def upsert_document(
    session: Session,
    *,
    source: Source,
    url: str,
    document_type: str,
    crawl_status: str,
    title: str | None,
    author: str | None,
    published_at,
    extracted_text: str | None,
    summary: str | None,
    topics: list[str],
    embedding: str | None,
    content_hash: str | None,
) -> Document:
    url = normalize_url(url)
    document = session.execute(select(Document).where(Document.url == url)).scalar_one_or_none()
    if document is None:
        document = Document(
            source_id=source.id,
            url=url,
        )
        session.add(document)
    document.source_id = source.id
    document.document_type = document_type
    document.crawl_status = crawl_status
    document.title = title
    document.author = author
    document.published_at = published_at
    document.extracted_text = extracted_text
    document.summary = summary
    document.topics = [topic for topic in topics if topic]
    document.embedding = embedding
    document.content_hash = content_hash
    document.last_crawled_at = datetime.now(timezone.utc)
    session.flush()
    return document


def upsert_link(
    session: Session,
    *,
    source_document: Document,
    target_url: str,
    anchor_text: str | None,
    context: str | None,
) -> Link:
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
