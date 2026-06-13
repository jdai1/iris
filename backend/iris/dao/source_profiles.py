"""DAO helpers for persisted source profile analysis."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from iris.dao import db
from iris.models import Document, Source, SourceProfileAnalysis
from iris.schemas.enums import CrawlStatus, DocumentType, SourceStatus


def get_source(source_id: int) -> Source | None:
    """Return a source by id."""
    return db.current_session().get(Source, source_id)


def get_source_by_domain(domain: str) -> Source | None:
    """Return a source by canonical domain."""
    return db.current_session().scalar(select(Source).where(Source.canonical_domain == domain))


def get_analysis(source_id: int) -> SourceProfileAnalysis | None:
    """Return cached profile analysis for a source."""
    return db.current_session().scalar(select(SourceProfileAnalysis).where(SourceProfileAnalysis.source_id == source_id))


def get_or_create_analysis(source: Source) -> SourceProfileAnalysis:
    """Return the existing analysis row or create one."""
    session = db.current_session()
    analysis = get_analysis(source.id)
    if analysis:
        return analysis
    analysis = SourceProfileAnalysis(source_id=source.id, status="pending")
    session.add(analysis)
    session.flush()
    return analysis


def upsert_analysis(
    source: Source,
    *,
    status: str,
    display_name: str | None,
    payload: dict | None,
    scraped_facts: dict | None,
    evidence_document_ids: list[int],
    unavailable_sections: list[str],
    model: str | None,
    input_fingerprint: str | None,
    error: str | None = None,
) -> SourceProfileAnalysis:
    """Persist a source profile analysis payload."""
    analysis = get_or_create_analysis(source)
    analysis.status = status
    analysis.display_name = display_name
    analysis.payload = payload
    analysis.scraped_facts = scraped_facts
    analysis.evidence_document_ids = evidence_document_ids
    analysis.unavailable_sections = unavailable_sections
    analysis.model = model
    analysis.input_fingerprint = input_fingerprint
    analysis.error = error
    analysis.generated_at = datetime.now(timezone.utc) if status == "succeeded" else None
    db.flush()
    return analysis


def get_documents_for_profile(source_id: int, *, limit: int = 500) -> list[Document]:
    """Return fetched source documents ordered for profile analysis."""
    session = db.current_session()
    return list(
        session.scalars(
            select(Document)
            .where(Document.source_id == source_id)
            .where(Document.crawl_status == CrawlStatus.FETCHED.value)
            .where(Document.document_type.in_([DocumentType.ESSAY.value, DocumentType.PROFILE.value, DocumentType.COLLECTION.value]))
            .order_by(Document.document_type.desc(), Document.published_at.desc().nullslast(), Document.id.desc())
            .limit(max(1, limit))
        )
    )


def get_sources_for_profile_backfill(*, limit: int | None = None) -> list[Source]:
    """Return indexed sources that have at least one fetched document."""
    statement = (
        select(Source)
        .join(Document, Document.source_id == Source.id)
        .where(Source.status == SourceStatus.INDEXED.value)
        .where(Document.crawl_status == CrawlStatus.FETCHED.value)
        .group_by(Source.id)
        .order_by(Source.last_checked_at.desc().nullslast(), Source.first_seen_at.desc())
    )
    if limit:
        statement = statement.limit(limit)
    return list(db.current_session().scalars(statement))
