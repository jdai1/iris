from __future__ import annotations

from datetime import date, datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from models.mixins import Base, TimestampMixin


class Domain(Base, TimestampMixin):
    __tablename__ = "domains"
    __table_args__ = (
        Index("idx_domains_excluded", "excluded"),
        Index("idx_domains_url", "domain_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    domain_url: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    entity: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)

    excluded: Mapped[bool] = mapped_column(default=False, nullable=False)
    reason: Mapped[str | None] = mapped_column(nullable=True)

    links: Mapped[list["Link"]] = relationship("Link", back_populates="domain")


class Link(Base, TimestampMixin):
    __tablename__ = "links"
    __table_args__ = (Index("idx_link_domain_id", "domain_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    domain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("domains.id"), nullable=False, index=True
    )
    domain: Mapped["Domain"] = relationship("Domain", back_populates="links")
    entry_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("entries.id"), nullable=True
    )
    # Relationship via Link.entry_id → Entry.id
    entry: Mapped[Entry | None] = relationship(
        "Entry",
        foreign_keys=[entry_id],
    )


class Entry(Base, TimestampMixin):
    __tablename__ = "entries"
    __table_args__ = (Index("idx_entries_link_id", "link_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("links.id"), unique=True, nullable=False, index=True
    )
    # Relationship via Entry.link_id → Link.id
    link: Mapped["Link"] = relationship(
        "Link",
        foreign_keys=[link_id],
    )
    title: Mapped[str] = mapped_column(nullable=False)
    summary: Mapped[str] = mapped_column(nullable=False)
    topics: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    author: Mapped[str] = mapped_column(nullable=False)
    date_published: Mapped[date | None] = mapped_column(nullable=True)


class LinkAliasMapping(Base, TimestampMixin):
    __tablename__ = "link_alias_mappings"
    __table_args__ = (
        Index("idx_link_alias_mappings_canonical_link", "canonical_link_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alias_url: Mapped[str] = mapped_column(unique=True, nullable=False, index=True)
    canonical_link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("links.id"), nullable=False, index=True
    )
    canonical_link: Mapped["Link"] = relationship(
        "Link",
        foreign_keys=[canonical_link_id],
    )


class LinkMapping(Base, TimestampMixin):
    __tablename__ = "link_mappings"
    __table_args__ = (
        UniqueConstraint("source_link_id", "target_link_id"),
        Index(
            "idx_link_mappings_source_target",
            "source_link_id",
            "target_link_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("links.id"), nullable=False, index=True
    )
    source_link: Mapped["Link"] = relationship(
        "Link",
        foreign_keys=[source_link_id],
    )
    target_link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("links.id"), nullable=False, index=True
    )
    target_link: Mapped["Link"] = relationship(
        "Link",
        foreign_keys=[target_link_id],
    )


class DomainAliasMapping(Base, TimestampMixin):
    __tablename__ = "domain_alias_mappings"
    __table_args__ = (
        Index(
            "idx_domain_alias_mappings_canonical_domain_id",
            "canonical_domain_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alias_domain_url: Mapped[str] = mapped_column(
        unique=True, nullable=False, index=True
    )
    canonical_domain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("domains.id"), nullable=False, index=True
    )
    canonical_domain: Mapped["Domain"] = relationship(
        "Domain",
        foreign_keys=[canonical_domain_id],
    )


class DomainMapping(Base, TimestampMixin):
    __tablename__ = "domain_mappings"
    __table_args__ = (
        UniqueConstraint("source_domain_id", "target_domain_id"),
        Index(
            "idx_domain_mappings_source_target",
            "source_domain_id",
            "target_domain_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_domain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("domains.id"), nullable=False, index=True
    )
    source_domain: Mapped["Domain"] = relationship(
        "Domain",
        foreign_keys=[source_domain_id],
    )
    target_domain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("domains.id"), nullable=False, index=True
    )
    target_domain: Mapped["Domain"] = relationship(
        "Domain",
        foreign_keys=[target_domain_id],
    )


class DomainLinkMapping(Base, TimestampMixin):
    __tablename__ = "domain_link_mappings"
    __table_args__ = (
        UniqueConstraint("link_id", "domain_id"),
        Index("idx_domain_link_mappings_link_domain", "link_id", "domain_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    link_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("links.id"), nullable=False, index=True
    )
    link: Mapped["Link"] = relationship("Link")
    domain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("domains.id"), nullable=False, index=True
    )
    domain: Mapped["Domain"] = relationship("Domain")
