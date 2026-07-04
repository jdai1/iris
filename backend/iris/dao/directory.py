"""Query helpers for directory table views."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.sql.elements import ColumnElement

from iris.dao import db
from iris.dao.admin import clamped_limit, count_statement
from iris.models import Document, Link, Source
from iris.schemas.api import DirectorySourceSchema
from iris.schemas.enums import DocumentType, SourceStatus


@dataclass(frozen=True)
class SourceDirectoryQuery:
    """Build the source directory table query from filter and sort inputs."""

    q: str | None = None
    status: str | None = SourceStatus.INDEXED.value
    sort: str = "inbound"
    direction: str = "desc"

    def statement(self) -> Select:
        doc_counts = (
            select(
                Document.source_id,
                func.count(Document.id).label("document_count"),
                func.count(Document.id).filter(Document.document_type == DocumentType.ESSAY.value).label("essay_count"),
            )
            .group_by(Document.source_id)
            .subquery()
        )
        inbound_counts = (
            select(Link.target_source_id.label("source_id"), func.count(Link.id).label("inbound_count"))
            .where(Link.target_source_id.is_not(None))
            .group_by(Link.target_source_id)
            .subquery()
        )
        outbound_counts = (
            select(Document.source_id, func.count(Link.id).label("outbound_count"))
            .join(Link, Link.source_document_id == Document.id)
            .group_by(Document.source_id)
            .subquery()
        )
        document_count = func.coalesce(doc_counts.c.document_count, 0).label("document_count")
        essay_count = func.coalesce(doc_counts.c.essay_count, 0).label("essay_count")
        inbound_count = func.coalesce(inbound_counts.c.inbound_count, 0).label("inbound_count")
        outbound_count = func.coalesce(outbound_counts.c.outbound_count, 0).label("outbound_count")
        statement = (
            select(
                Source,
                document_count,
                essay_count,
                inbound_count,
                outbound_count,
            )
            .outerjoin(doc_counts, doc_counts.c.source_id == Source.id)
            .outerjoin(inbound_counts, inbound_counts.c.source_id == Source.id)
            .outerjoin(outbound_counts, outbound_counts.c.source_id == Source.id)
        )
        if self.status and self.status != "all":
            statement = statement.where(Source.status == self.status)
        if self.q and self.q.strip():
            pattern = f"%{self.q.strip()}%"
            statement = statement.where(
                Source.canonical_domain.ilike(pattern)
                | Source.name.ilike(pattern)
                | Source.description.ilike(pattern)
            )
        return statement.order_by(*self._order_by(document_count, essay_count, inbound_count, outbound_count))

    def _order_by(
        self,
        document_count: ColumnElement,
        essay_count: ColumnElement,
        inbound_count: ColumnElement,
        outbound_count: ColumnElement,
    ):
        descending = self.direction != "asc"
        if self.sort == "source":
            return (Source.canonical_domain.desc() if descending else Source.canonical_domain.asc(),)
        if self.sort == "documents":
            ordered = document_count.desc() if descending else document_count.asc()
            return (ordered, Source.canonical_domain.asc())
        if self.sort == "essays":
            ordered = essay_count.desc() if descending else essay_count.asc()
            return (ordered, Source.canonical_domain.asc())
        if self.sort == "outbound":
            ordered = outbound_count.desc() if descending else outbound_count.asc()
            return (ordered, Source.canonical_domain.asc())
        if self.sort == "recent":
            ordered = Source.last_checked_at.desc().nullslast() if descending else Source.last_checked_at.asc().nullsfirst()
            return (ordered, Source.first_seen_at.desc())
        ordered = inbound_count.desc() if descending else inbound_count.asc()
        return (ordered, Source.canonical_domain.asc())


def get_source_directory_page(*, q: str | None, status: str | None, sort: str, direction: str, limit: int, offset: int) -> tuple[list[DirectorySourceSchema], int]:
    """Return source directory rows; default ranking is most referenced sources."""
    session = db.current_session()
    statement = SourceDirectoryQuery(q=q, status=status, sort=sort, direction=direction).statement()
    total = count_statement(statement)
    rows = session.execute(statement.limit(clamped_limit(limit)).offset(max(offset, 0))).all()
    items = [
        DirectorySourceSchema(
            id=source.id,
            canonical_domain=source.canonical_domain,
            url=source.url,
            name=source.name,
            status=source.status,
            description=source.description,
            first_seen_at=source.first_seen_at,
            last_checked_at=source.last_checked_at,
            document_count=int(document_count or 0),
            essay_count=int(essay_count or 0),
            inbound_count=int(inbound_count or 0),
            outbound_count=int(outbound_count or 0),
        )
        for source, document_count, essay_count, inbound_count, outbound_count in rows
    ]
    return items, total
