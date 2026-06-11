from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    homepage_url: Mapped[str] = mapped_column(Text)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    discovered_from_source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id"), nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rss_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sitemap_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    documents: Mapped[list["Document"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("final_url", name="uq_documents_final_url"),
        Index("idx_documents_type_status", "document_type", "crawl_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), index=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    document_type: Mapped[str] = mapped_column(String(40), default="unknown", index=True)
    crawl_status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    topics: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)
    last_crawled_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    source: Mapped[Source] = relationship(back_populates="documents")
    outgoing_links: Mapped[list["Link"]] = relationship(
        back_populates="source_document",
        cascade="all, delete-orphan",
        foreign_keys="Link.source_document_id",
    )


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        UniqueConstraint("source_document_id", "normalized_target_url", name="uq_links_source_target"),
        Index("idx_links_target_domain", "target_domain"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    target_url: Mapped[str] = mapped_column(Text)
    normalized_target_url: Mapped[str] = mapped_column(Text)
    target_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)
    target_document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), nullable=True, index=True)
    anchor_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    link_type: Mapped[str] = mapped_column(String(20), default="external", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)

    source_document: Mapped[Document] = relationship(foreign_keys=[source_document_id], back_populates="outgoing_links")


class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"), index=True)
    index_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("index_runs.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    pages_queued: Mapped[int] = mapped_column(Integer, default=0)
    pages_fetched: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)
    documents_indexed: Mapped[int] = mapped_column(Integer, default=0)
    links_seen: Mapped[int] = mapped_column(Integer, default=0)
    sources_discovered: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class IndexRun(Base):
    __tablename__ = "index_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(40), default="running", index=True)
    mode: Mapped[str] = mapped_column(String(40), default="autopilot", index=True)
    dry_run: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
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
    stop_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class IndexEvent(Base):
    __tablename__ = "index_events"
    __table_args__ = (
        Index("idx_index_events_run_created", "index_run_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    index_run_id: Mapped[int] = mapped_column(ForeignKey("index_runs.id"), index=True)
    source_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sources.id"), nullable=True, index=True)
    crawl_job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crawl_jobs.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Search(Base):
    __tablename__ = "searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(Text)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class SearchResult(Base):
    __tablename__ = "search_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    search_id: Mapped[int] = mapped_column(ForeignKey("searches.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)


class DigestItem(Base):
    __tablename__ = "digest_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    shown_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    document: Mapped[Document] = relationship(foreign_keys=[document_id])


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    surface: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40), index=True)
    search_id: Mapped[Optional[int]] = mapped_column(ForeignKey("searches.id"), nullable=True)
    digest_item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("digest_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
