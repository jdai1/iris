from __future__ import annotations

from datetime import datetime

from sqlalchemy import Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iris.dao.db import Base
from iris.models.sqla import Document, enum_type, utcnow
from iris.schemas.enums import (
    AgentMessageRole,
    BookshelfCollectionVisibility,
    BookshelfStatus,
    CategoryAssignmentSource,
    CategoryStatus,
    TagScope,
)


class User(Base):
    """A local or authenticated Iris user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    document_mappings: Mapped[list["UserDocumentMapping"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    bookshelf_collections: Mapped[list["BookshelfCollection"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tags: Mapped[list["Tag"]] = relationship(
        back_populates="user", foreign_keys="Tag.user_id"
    )
    agent_conversations: Mapped[list["AgentConversation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserDocumentMapping(Base):
    """Per-user state for one document."""

    __tablename__ = "user_document_mappings"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "document_id", name="uq_user_document_mappings_user_document"
        ),
        Index("idx_user_document_mappings_user_favorite", "user_id", "favorited_at"),
        Index("idx_user_document_mappings_user_read", "user_id", "read_at"),
        Index("idx_user_document_mappings_user_dismissed", "user_id", "dismissed_at"),
        Index("idx_user_document_mappings_user_bookshelf", "user_id", "bookshelf_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)
    first_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(nullable=True)
    first_opened_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_opened_at: Mapped[datetime | None] = mapped_column(nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)
    favorited_at: Mapped[datetime | None] = mapped_column(nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    bookshelf_status: Mapped[BookshelfStatus | None] = mapped_column(
        enum_type(BookshelfStatus, "bookshelf_status"), nullable=True, index=True
    )

    open_count: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    intent_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="document_mappings")
    document: Mapped[Document] = relationship(foreign_keys=[document_id])


class BookshelfCollection(Base):
    """A user-curated collection of bookshelf entries."""

    __tablename__ = "bookshelf_collections"
    __table_args__ = (
        UniqueConstraint("share_token", name="uq_bookshelf_collections_share_token"),
        Index("idx_bookshelf_collections_user_updated", "user_id", "updated_at"),
        Index("idx_bookshelf_collections_visibility", "visibility"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    visibility: Mapped[BookshelfCollectionVisibility] = mapped_column(
        enum_type(BookshelfCollectionVisibility, "bookshelf_collection_visibility"),
        default=BookshelfCollectionVisibility.PRIVATE,
        index=True,
    )
    share_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)

    user: Mapped[User] = relationship(back_populates="bookshelf_collections")
    items: Mapped[list["BookshelfCollectionItem"]] = relationship(
        back_populates="collection", cascade="all, delete-orphan", order_by="BookshelfCollectionItem.position"
    )


class BookshelfCollectionItem(Base):
    """One document in a user-created bookshelf collection."""

    __tablename__ = "bookshelf_collection_items"
    __table_args__ = (
        UniqueConstraint("collection_id", "document_id", name="uq_bookshelf_collection_items_collection_document"),
        Index("idx_bookshelf_collection_items_collection_position", "collection_id", "position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(ForeignKey("bookshelf_collections.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    position: Mapped[int] = mapped_column(Integer, default=0)

    collection: Mapped[BookshelfCollection] = relationship(back_populates="items")
    document: Mapped[Document] = relationship(foreign_keys=[document_id])


class Tag(Base):
    """A system-generated or user-created document tag."""

    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("namespace", "slug", name="uq_tags_namespace_slug"),
        Index("idx_tags_scope_slug", "scope", "slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    scope: Mapped[TagScope] = mapped_column(
        enum_type(TagScope, "tag_scope"), index=True
    )
    namespace: Mapped[str] = mapped_column(String(160), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)

    user: Mapped[User | None] = relationship(
        back_populates="tags", foreign_keys=[user_id]
    )


class DocumentTag(Base):
    """A system or user tag assignment for one document."""

    __tablename__ = "document_tags"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "tag_id",
            "assignment_namespace",
            name="uq_document_tags_document_tag_namespace",
        ),
        Index("idx_document_tags_tag_document", "tag_id", "document_id"),
        Index("idx_document_tags_assignment_namespace", "assignment_namespace"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), index=True)
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    assignment_namespace: Mapped[str] = mapped_column(String(160), index=True)

    document: Mapped[Document] = relationship(foreign_keys=[document_id])
    tag: Mapped[Tag] = relationship(foreign_keys=[tag_id])
    assigned_by_user: Mapped[User | None] = relationship(
        foreign_keys=[assigned_by_user_id]
    )


class Category(Base):
    """A system-managed high-level topic category."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_categories_slug"),
        Index("idx_categories_status_slug", "status", "slug"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CategoryStatus] = mapped_column(
        enum_type(CategoryStatus, "category_status"), default=CategoryStatus.ACTIVE, index=True
    )
    color: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DocumentCategoryAssignment(Base):
    """A system category assignment for one document."""

    __tablename__ = "document_categories"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "category_id",
            name="uq_document_categories_document_category",
        ),
        Index(
            "idx_document_categories_category_document", "category_id", "document_id"
        ),
        Index("idx_document_categories_primary", "document_id", "is_primary"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    is_primary: Mapped[int] = mapped_column(Integer, default=0, index=True)
    assigned_by: Mapped[CategoryAssignmentSource] = mapped_column(
        enum_type(CategoryAssignmentSource, "category_assignment_source"),
        default=CategoryAssignmentSource.SYSTEM,
        index=True,
    )

    document: Mapped[Document] = relationship(foreign_keys=[document_id])
    category: Mapped[Category] = relationship(foreign_keys=[category_id])


class AgentConversation(Base):
    """A persisted agentic search chat for the local user."""

    __tablename__ = "agent_conversations"
    __table_args__ = (Index("idx_agent_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="agent_conversations")
    messages: Mapped[list["AgentMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="AgentMessage.id"
    )


class AgentMessage(Base):
    """One user or assistant message in an agent conversation."""

    __tablename__ = "agent_messages"
    __table_args__ = (Index("idx_agent_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("agent_conversations.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    role: Mapped[AgentMessageRole] = mapped_column(
        enum_type(AgentMessageRole, "agent_message_role"), index=True
    )
    content: Mapped[str] = mapped_column(Text)
    steps: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)

    conversation: Mapped[AgentConversation] = relationship(back_populates="messages")
    results: Mapped[list["AgentSearchResult"]] = relationship(
        back_populates="message", cascade="all, delete-orphan", order_by="AgentSearchResult.rank"
    )


class AgentSearchResult(Base):
    """A ranked document citation stored for an assistant message."""

    __tablename__ = "agent_search_results"
    __table_args__ = (
        UniqueConstraint("message_id", "document_id", name="uq_agent_results_message_document"),
        Index("idx_agent_results_message_rank", "message_id", "rank"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("agent_messages.id"), index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)

    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(Text)

    message: Mapped[AgentMessage] = relationship(back_populates="results")
    document: Mapped[Document] = relationship(foreign_keys=[document_id])
