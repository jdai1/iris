"""Persistence helpers for source rows."""

from __future__ import annotations

from sqlalchemy import select

from iris.dao import db
from iris.models import Source
from iris.schemas.enums import SourceStatus
from iris.services.common.url_utils import domain_for_url, normalize_url, root_url_for_domain


def get_or_create_source(
    url: str,
    *,
    status: str = SourceStatus.QUEUED.value,
    discovered_from_source_id: int | None = None,
    force_status: bool = False,
) -> Source:
    """Return an existing source for a URL or create its canonical source row."""
    session = db.current_session()
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
