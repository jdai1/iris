"""DAO helpers for local-user document state and tags."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select

from iris.dao import db
from iris.models import Document, DocumentCategory, DocumentTag, Tag, TagScope, User, UserDocumentMapping
from iris.services.auth import FirebaseIdentity


LOCAL_USER_EMAIL = "local@iris.local"
SYSTEM_NAMESPACE = "system"


CATEGORY_KEYWORDS: dict[DocumentCategory, set[str]] = {
    DocumentCategory.SCIENCE: {"science", "biology", "physics", "chemistry", "neuroscience", "research", "statistics"},
    DocumentCategory.TECHNOLOGY: {"technology", "ai", "ml", "machine learning", "neuralink", "internet"},
    DocumentCategory.SOFTWARE: {"software", "programming", "code", "engineering", "developer", "database", "postgres"},
    DocumentCategory.STARTUPS: {"startup", "startups", "venture", "vc", "company", "product", "management"},
    DocumentCategory.PHILOSOPHY: {"philosophy", "ethics", "epistemology", "rationality", "thinking"},
    DocumentCategory.HISTORY: {"history", "war", "cold-war", "olympics", "ancient"},
    DocumentCategory.POLITICS: {"politics", "policy", "government", "geopolitics", "election"},
    DocumentCategory.ECONOMICS: {"economics", "econ", "markets", "finance", "money"},
    DocumentCategory.HEALTH: {"health", "medicine", "medical", "fitness", "nutrition"},
    DocumentCategory.CULTURE: {"culture", "media", "film", "book", "review", "art"},
    DocumentCategory.PERSONAL: {"personal", "life", "career", "writing", "reflection"},
}


def get_or_create_local_user() -> User:
    """Return the singleton local user row."""
    session = db.current_session()
    user = session.execute(select(User).where(User.email == LOCAL_USER_EMAIL)).scalar_one_or_none()
    if user:
        return user
    user = User(email=LOCAL_USER_EMAIL, display_name="Local")
    session.add(user)
    session.flush()
    return user


def get_or_create_firebase_user(identity: FirebaseIdentity) -> User:
    """Return the Iris user mapped to a Firebase user, creating it when needed."""
    session = db.current_session()
    user = session.execute(
        select(User).where(User.firebase_uid == identity.uid)
    ).scalar_one_or_none()
    if user is None:
        email = _identity_email(identity)
        user = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            user = User(email=email, firebase_uid=identity.uid)
            session.add(user)
        else:
            user.firebase_uid = identity.uid
    user.email = _identity_email(identity)
    user.display_name = identity.display_name or identity.email or user.email
    user.photo_url = identity.photo_url
    session.flush()
    return user


def _identity_email(identity: FirebaseIdentity) -> str:
    if identity.email:
        return identity.email.lower()
    return f"{identity.uid.lower()}@firebase.local"


def get_or_create_user_document_mapping(user: User, document: Document) -> UserDocumentMapping:
    """Return the per-user document mapping row, creating it when needed."""
    session = db.current_session()
    mapping = session.execute(
        select(UserDocumentMapping).where(
            UserDocumentMapping.user_id == user.id,
            UserDocumentMapping.document_id == document.id,
        )
    ).scalar_one_or_none()
    if mapping:
        return mapping
    now = datetime.now(timezone.utc)
    mapping = UserDocumentMapping(
        user_id=user.id,
        document_id=document.id,
        first_seen_at=now,
        last_seen_at=now,
    )
    session.add(mapping)
    session.flush()
    return mapping


def slugify_tag_name(name: str) -> str:
    """Normalize a tag name into a stable slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "untitled"


def get_or_create_tag(
    name: str,
    *,
    scope: TagScope = TagScope.SYSTEM,
    user: User | None = None,
    color: str | None = None,
) -> Tag:
    """Return a tag in the requested namespace, creating it when needed."""
    session = db.current_session()
    slug = slugify_tag_name(name)
    namespace = SYSTEM_NAMESPACE if scope == TagScope.SYSTEM else f"user:{user.id if user else 'unknown'}"
    tag = session.execute(select(Tag).where(Tag.namespace == namespace, Tag.slug == slug)).scalar_one_or_none()
    if tag:
        return tag
    tag = Tag(
        user_id=user.id if user else None,
        scope=scope,
        namespace=namespace,
        name=name.strip(),
        slug=slug,
        color=color,
    )
    session.add(tag)
    session.flush()
    return tag


def tag_document(
    document: Document,
    tag: Tag,
    *,
    assigned_by_user: User | None = None,
) -> DocumentTag:
    """Assign a tag to a document if that assignment does not already exist."""
    session = db.current_session()
    assignment_namespace = SYSTEM_NAMESPACE if assigned_by_user is None else f"user:{assigned_by_user.id}"
    document_tag = session.execute(
        select(DocumentTag).where(
            DocumentTag.document_id == document.id,
            DocumentTag.tag_id == tag.id,
            DocumentTag.assignment_namespace == assignment_namespace,
        )
    ).scalar_one_or_none()
    if document_tag:
        return document_tag
    document_tag = DocumentTag(
        document_id=document.id,
        tag_id=tag.id,
        assigned_by_user_id=assigned_by_user.id if assigned_by_user else None,
        assignment_namespace=assignment_namespace,
    )
    session.add(document_tag)
    session.flush()
    return document_tag


def classify_document_category(document: Document) -> DocumentCategory:
    """Infer a broad document category from stored metadata."""
    text = " ".join(
        item
        for item in [
            document.title or "",
            document.summary or "",
            " ".join(document.topics or []),
        ]
        if item
    ).lower()
    if not text.strip():
        return DocumentCategory.UNKNOWN
    scores = {
        category: sum(1 for keyword in keywords if keyword in text)
        for category, keywords in CATEGORY_KEYWORDS.items()
    }
    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score > 0 else DocumentCategory.UNKNOWN
