from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.dao.db import Base
from iris.schemas.enums import (
    CrawlJobStatus,
    CrawlStatus,
    DocumentCategory,
    DocumentType,
    IndexEventType,
    IndexMode,
    IndexRunStatus,
    LinkType,
    SourceStatus,
    StringEnum,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_values(enum_class: type[StringEnum]) -> list[str]:
    return [item.value for item in enum_class]


def enum_type(enum_class: type[StringEnum], name: str, length: int = 40) -> SqlEnum:
    return SqlEnum(
        enum_class,
        values_callable=enum_values,
        native_enum=False,
        validate_strings=True,
        create_constraint=True,
        name=name,
        length=length,
    )


class Source(Base):
    """A crawlable web origin, usually a domain-level blog or essay archive."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    discovered_from_source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    canonical_domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_checked_at: Mapped[datetime | None] = mapped_column(nullable=True)

    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[SourceStatus] = mapped_column(enum_type(SourceStatus, "source_status"), default=SourceStatus.QUEUED, index=True)
    rss_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    sitemap_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list["Document"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Document(Base):
    """A fetched page from a source, including extracted text and search metadata."""

    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("url", name="uq_documents_url"),
        Index("idx_documents_type_status", "document_type", "crawl_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    crawl_job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"), nullable=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)

    crawl_status: Mapped[CrawlStatus] = mapped_column(enum_type(CrawlStatus, "crawl_status"), default=CrawlStatus.PENDING, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_crawled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)
    
    document_type: Mapped[DocumentType] = mapped_column(enum_type(DocumentType, "document_type"), default=DocumentType.UNKNOWN, index=True)
    category: Mapped[DocumentCategory] = mapped_column(enum_type(DocumentCategory, "document_category"), default=DocumentCategory.UNKNOWN, index=True)
    
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    
    source: Mapped[Source] = relationship(back_populates="documents")
    outgoing_links: Mapped[list["Link"]] = relationship(
        back_populates="source_document",
        cascade="all, delete-orphan",
        foreign_keys="Link.source_document_id",
    )


class Link(Base):
    """A normalized hyperlink extracted from one document to another URL."""

    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint("source_document_id", "target_url", name="uq_links_source_target"),
        Index("idx_links_target_domain", "target_domain"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    target_source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)
    target_document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)

    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)

    target_url: Mapped[str] = mapped_column(Text)
    target_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_type: Mapped[LinkType] = mapped_column(enum_type(LinkType, "link_type", length=20), default=LinkType.EXTERNAL, index=True)

    source_document: Mapped[Document] = relationship(foreign_keys=[source_document_id], back_populates="outgoing_links")


class CrawlJob(Base):
    """One crawl attempt for a source, optionally attached to an autopilot index run."""

    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    index_run_id: Mapped[int | None] = mapped_column(ForeignKey("index_runs.id"), nullable=True, index=True)

    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    status: Mapped[CrawlJobStatus] = mapped_column(enum_type(CrawlJobStatus, "crawl_job_status"), default=CrawlJobStatus.RUNNING, index=True)
    pages_queued: Mapped[int] = mapped_column(Integer, default=0)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    documents_indexed: Mapped[int] = mapped_column(Integer, default=0)
    links_seen: Mapped[int] = mapped_column(Integer, default=0)
    sources_discovered: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class IndexRun(Base):
    """A top-level indexing/autopilot run that plans and executes source crawls."""

    __tablename__ = "index_runs"

    id: Mapped[int] = mapped_column(primary_key=True)

    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)

    status: Mapped[IndexRunStatus] = mapped_column(enum_type(IndexRunStatus, "index_run_status"), default=IndexRunStatus.RUNNING, index=True)
    mode: Mapped[IndexMode] = mapped_column(enum_type(IndexMode, "index_mode"), default=IndexMode.AUTOPILOT, index=True)
    dry_run: Mapped[int] = mapped_column(Integer, default=0)
    budget_sources: Mapped[int] = mapped_column(Integer, default=0)
    max_pages: Mapped[int] = mapped_column(Integer, default=0)
    max_depth: Mapped[int] = mapped_column(Integer, default=0)
    planned_sources: Mapped[int] = mapped_column(Integer, default=0)
    attempted_sources: Mapped[int] = mapped_column(Integer, default=0)
    crawled_sources: Mapped[int] = mapped_column(Integer, default=0)
    ignored_sources: Mapped[int] = mapped_column(Integer, default=0)
    documents_indexed: Mapped[int] = mapped_column(Integer, default=0)
    links_seen: Mapped[int] = mapped_column(Integer, default=0)
    sources_discovered: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class IndexEvent(Base):
    """Structured telemetry emitted while planning and crawling an index run."""

    __tablename__ = "index_events"
    __table_args__ = (
        Index("idx_index_events_run_created", "index_run_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    index_run_id: Mapped[int] = mapped_column(ForeignKey("index_runs.id"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)
    crawl_job_id: Mapped[int | None] = mapped_column(ForeignKey("crawl_jobs.id"), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    event_type: Mapped[IndexEventType] = mapped_column(enum_type(IndexEventType, "index_event_type", length=80), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[str | None] = mapped_column(Text, nullable=True)
