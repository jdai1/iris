"""Persistence helpers for user bookshelf entries and collections."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import joinedload

from iris.dao import db
from iris.dao.documents import upsert_document
from iris.dao.sources import get_or_create_source
from iris.dao.user_state import get_or_create_tag, get_or_create_user_document_mapping, tag_document
from iris.models import (
    BookshelfCollection,
    BookshelfCollectionItem,
    BookshelfCollectionVisibility,
    BookshelfStatus,
    Document,
    DocumentTag,
    SourceStatus,
    Tag,
    TagScope,
    User,
    UserDocumentMapping,
)
from iris.schemas.enums import CrawlStatus, DocumentType
from iris.services.common.url_utils import is_valid_http_url, normalize_url


def effective_status(mapping: UserDocumentMapping) -> BookshelfStatus:
    """Return explicit bookshelf status, falling back to legacy timestamp fields."""
    if mapping.bookshelf_status:
        return mapping.bookshelf_status
    if mapping.dismissed_at:
        return BookshelfStatus.ARCHIVED
    if mapping.read_at:
        return BookshelfStatus.READ
    return BookshelfStatus.SAVED


def list_entries(
    user: User,
    *,
    status: BookshelfStatus | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[UserDocumentMapping], int]:
    """Return one page of bookshelf entries for a user."""
    session = db.current_session()
    statement = (
        select(UserDocumentMapping)
        .options(joinedload(UserDocumentMapping.document).joinedload(Document.source))
        .where(UserDocumentMapping.user_id == user.id)
    )
    if status == BookshelfStatus.ARCHIVED:
        statement = statement.where(
            (UserDocumentMapping.bookshelf_status == BookshelfStatus.ARCHIVED.value)
            | (UserDocumentMapping.dismissed_at.is_not(None))
        )
    elif status == BookshelfStatus.READ:
        statement = statement.where(
            (UserDocumentMapping.bookshelf_status == BookshelfStatus.READ.value)
            | (
                (UserDocumentMapping.bookshelf_status.is_(None))
                & (UserDocumentMapping.read_at.is_not(None))
                & (UserDocumentMapping.dismissed_at.is_(None))
            )
        )
    elif status == BookshelfStatus.SAVED:
        statement = statement.where(
            (UserDocumentMapping.bookshelf_status == BookshelfStatus.SAVED.value)
            | (
                (UserDocumentMapping.bookshelf_status.is_(None))
                & (UserDocumentMapping.read_at.is_(None))
                & (UserDocumentMapping.dismissed_at.is_(None))
            )
        )
    else:
        statement = statement.where(
            (UserDocumentMapping.bookshelf_status.is_not(None))
            | (UserDocumentMapping.read_at.is_not(None))
            | (UserDocumentMapping.favorited_at.is_not(None))
            | (UserDocumentMapping.dismissed_at.is_not(None))
        )
    statement = statement.order_by(UserDocumentMapping.updated_at.desc(), UserDocumentMapping.id.desc())
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.execute(statement.limit(max(limit, 0)).offset(max(offset, 0))).scalars().all()
    return items, total


def favorite_entries(user: User, *, limit: int = 100, offset: int = 0) -> tuple[list[UserDocumentMapping], int]:
    """Return one page of favorited bookshelf entries."""
    session = db.current_session()
    statement = (
        select(UserDocumentMapping)
        .options(joinedload(UserDocumentMapping.document).joinedload(Document.source))
        .where(UserDocumentMapping.user_id == user.id)
        .where(UserDocumentMapping.favorited_at.is_not(None))
        .order_by(UserDocumentMapping.favorited_at.desc(), UserDocumentMapping.id.desc())
    )
    total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = session.execute(statement.limit(max(limit, 0)).offset(max(offset, 0))).scalars().all()
    return items, total


def save_document(user: User, document: Document) -> UserDocumentMapping:
    """Save a document to the user's bookshelf if needed."""
    now = datetime.now(timezone.utc)
    mapping = get_or_create_user_document_mapping(user, document)
    if mapping.first_seen_at is None:
        mapping.first_seen_at = now
    mapping.last_seen_at = now
    if mapping.bookshelf_status is None or mapping.bookshelf_status == BookshelfStatus.ARCHIVED:
        mapping.bookshelf_status = BookshelfStatus.SAVED
        mapping.dismissed_at = None
    mapping.updated_at = now
    db.current_session().flush()
    return mapping


def update_entry(
    user: User,
    document: Document,
    *,
    status: BookshelfStatus | None = None,
    favorited: bool | None = None,
    note: str | None = None,
    intent_note: str | None = None,
    tags: list[str] | None = None,
    update_note: bool = False,
    update_intent_note: bool = False,
) -> UserDocumentMapping:
    """Update one user's bookshelf state for a document."""
    now = datetime.now(timezone.utc)
    mapping = save_document(user, document)
    if status:
        mapping.bookshelf_status = status
        if status == BookshelfStatus.READ:
            mapping.read_at = mapping.read_at or now
            mapping.dismissed_at = None
        elif status == BookshelfStatus.ARCHIVED:
            mapping.dismissed_at = mapping.dismissed_at or now
        elif status == BookshelfStatus.SAVED:
            mapping.dismissed_at = None
    if favorited is not None:
        mapping.favorited_at = now if favorited else None
    if update_note:
        mapping.note = _clean_optional_text(note)
    if update_intent_note:
        mapping.intent_note = _clean_optional_text(intent_note)
    if tags is not None:
        replace_user_tags(user, document, tags)
    mapping.updated_at = now
    db.current_session().flush()
    return mapping


def create_entry_for_url(
    user: User,
    *,
    url: str,
    title: str | None = None,
    note: str | None = None,
    intent_note: str | None = None,
    tags: list[str] | None = None,
) -> UserDocumentMapping:
    """Capture an arbitrary URL as a source/document and save it to the bookshelf."""
    normalized_url = normalize_url(url)
    if not is_valid_http_url(normalized_url):
        raise ValueError("Expected a valid http(s) URL")
    source = get_or_create_source(normalized_url, status=SourceStatus.QUEUED.value)
    document = upsert_document(
        source=source,
        url=normalized_url,
        document_type=DocumentType.UNKNOWN.value,
        crawl_status=CrawlStatus.PENDING.value,
        title=_clean_optional_text(title),
        author=None,
        published_at=None,
        extracted_text=None,
        summary=None,
        topics=[],
        embedding=None,
        content_hash=None,
    )
    return update_entry(
        user,
        document,
        note=note,
        intent_note=intent_note,
        tags=tags,
        update_note=True,
        update_intent_note=True,
    )


def user_tags_for_documents(user: User, document_ids: list[int]) -> dict[int, list[str]]:
    """Return user-assigned tag names keyed by document id."""
    if not document_ids:
        return {}
    namespace = _user_namespace(user)
    rows = (
        db.current_session()
        .execute(
            select(DocumentTag.document_id, Tag.name)
            .join(Tag, Tag.id == DocumentTag.tag_id)
            .where(DocumentTag.document_id.in_(document_ids))
            .where(DocumentTag.assignment_namespace == namespace)
            .order_by(Tag.name.asc())
        )
        .all()
    )
    tags: dict[int, list[str]] = {document_id: [] for document_id in document_ids}
    for document_id, name in rows:
        tags.setdefault(document_id, []).append(name)
    return tags


def replace_user_tags(user: User, document: Document, names: list[str]) -> None:
    """Replace all user tag assignments for a document."""
    session = db.current_session()
    namespace = _user_namespace(user)
    session.execute(
        delete(DocumentTag).where(
            DocumentTag.document_id == document.id,
            DocumentTag.assignment_namespace == namespace,
        )
    )
    seen: set[str] = set()
    for name in names:
        cleaned = name.strip()
        if not cleaned:
            continue
        slug_key = cleaned.lower()
        if slug_key in seen:
            continue
        seen.add(slug_key)
        tag = get_or_create_tag(cleaned, scope=TagScope.USER, user=user)
        tag_document(document, tag, assigned_by_user=user)
    session.flush()


def list_collections(user: User) -> list[BookshelfCollection]:
    """Return the user's collections with items loaded."""
    return (
        db.current_session()
        .execute(
            select(BookshelfCollection)
            .options(
                joinedload(BookshelfCollection.items)
                .joinedload(BookshelfCollectionItem.document)
                .joinedload(Document.source)
            )
            .where(BookshelfCollection.user_id == user.id)
            .order_by(BookshelfCollection.updated_at.desc(), BookshelfCollection.id.desc())
        )
        .unique()
        .scalars()
        .all()
    )


def create_collection(
    user: User,
    *,
    name: str,
    description: str | None,
    visibility: BookshelfCollectionVisibility,
) -> BookshelfCollection:
    """Create a bookshelf collection."""
    collection = BookshelfCollection(
        user_id=user.id,
        name=_required_name(name),
        description=_clean_optional_text(description),
        visibility=visibility,
        share_token=_new_share_token() if visibility == BookshelfCollectionVisibility.SHARE_LINK else None,
    )
    db.current_session().add(collection)
    db.current_session().flush()
    return collection


def update_collection(
    user: User,
    collection_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    visibility: BookshelfCollectionVisibility | None = None,
    update_name: bool = False,
    update_description: bool = False,
) -> BookshelfCollection | None:
    """Update a user-owned collection."""
    collection = get_collection(user, collection_id)
    if collection is None:
        return None
    if update_name:
        collection.name = _required_name(name or "")
    if update_description:
        collection.description = _clean_optional_text(description)
    if visibility is not None:
        collection.visibility = visibility
        if visibility == BookshelfCollectionVisibility.SHARE_LINK and not collection.share_token:
            collection.share_token = _new_share_token()
        if visibility == BookshelfCollectionVisibility.PRIVATE:
            collection.share_token = None
    collection.updated_at = datetime.now(timezone.utc)
    db.current_session().flush()
    return collection


def get_collection(user: User, collection_id: int) -> BookshelfCollection | None:
    """Return a user-owned collection by id."""
    return (
        db.current_session()
        .execute(
            select(BookshelfCollection)
            .options(
                joinedload(BookshelfCollection.items)
                .joinedload(BookshelfCollectionItem.document)
                .joinedload(Document.source)
            )
            .where(BookshelfCollection.id == collection_id)
            .where(BookshelfCollection.user_id == user.id)
        )
        .unique()
        .scalar_one_or_none()
    )


def get_shared_collection(share_token: str) -> BookshelfCollection | None:
    """Return a share-link collection by token."""
    return (
        db.current_session()
        .execute(
            select(BookshelfCollection)
            .options(
                joinedload(BookshelfCollection.items)
                .joinedload(BookshelfCollectionItem.document)
                .joinedload(Document.source)
            )
            .where(BookshelfCollection.share_token == share_token)
            .where(BookshelfCollection.visibility == BookshelfCollectionVisibility.SHARE_LINK.value)
        )
        .unique()
        .scalar_one_or_none()
    )


def add_collection_item(
    user: User,
    collection_id: int,
    document: Document,
    *,
    position: int | None = None,
) -> BookshelfCollectionItem | None:
    """Add a document to a user-owned collection."""
    session = db.current_session()
    collection = get_collection(user, collection_id)
    if collection is None:
        return None
    save_document(user, document)
    existing = session.execute(
        select(BookshelfCollectionItem).where(
            BookshelfCollectionItem.collection_id == collection.id,
            BookshelfCollectionItem.document_id == document.id,
        )
    ).scalar_one_or_none()
    if existing:
        if position is not None:
            existing.position = position
        return existing
    if position is None:
        position = (
            session.scalar(
                select(func.coalesce(func.max(BookshelfCollectionItem.position), -1)).where(
                    BookshelfCollectionItem.collection_id == collection.id
                )
            )
            or -1
        ) + 1
    item = BookshelfCollectionItem(collection_id=collection.id, document_id=document.id, position=position)
    collection.updated_at = datetime.now(timezone.utc)
    session.add(item)
    session.flush()
    return item


def remove_collection_item(user: User, collection_id: int, document_id: int) -> bool:
    """Remove a document from a user-owned collection."""
    session = db.current_session()
    collection = get_collection(user, collection_id)
    if collection is None:
        return False
    result = session.execute(
        delete(BookshelfCollectionItem).where(
            BookshelfCollectionItem.collection_id == collection.id,
            BookshelfCollectionItem.document_id == document_id,
        )
    )
    collection.updated_at = datetime.now(timezone.utc)
    session.flush()
    return (result.rowcount or 0) > 0


def _user_namespace(user: User) -> str:
    return f"user:{user.id}"


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _required_name(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Name is required")
    return stripped


def _new_share_token() -> str:
    return secrets.token_urlsafe(24)
