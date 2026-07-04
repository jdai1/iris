from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from iris.backfills.user_state import (
    backfill_document_categories,
    backfill_system_tags_from_topics,
)
from iris.dao.categories import (
    assign_category,
    get_or_create_category,
    seed_default_categories,
)
from iris.dao.user_state import (
    SYSTEM_NAMESPACE,
    classify_document_category,
    get_or_create_local_user,
    get_or_create_tag,
    get_or_create_user_document_mapping,
    tag_document,
)
from iris.models import (
    Category,
    DocumentCategory,
    DocumentCategoryAssignment,
    DocumentTag,
    Tag,
    TagScope,
    User,
    UserDocumentMapping,
)
from iris.dao.sources import get_or_create_source
from iris.dao.documents import upsert_document


def add_doc(session, title: str, text: str, topics: list[str] | None = None):
    source = get_or_create_source("https://state.test", status="indexed")
    return upsert_document(
        source=source,
        url=f"https://state.test/{title.lower().replace(' ', '-')}",
        document_type="essay",
        crawl_status="fetched",
        title=title,
        author=None,
        published_at=None,
        extracted_text=text,
        summary=text[:200],
        topics=topics or [],
        embedding=None,
        content_hash=title,
    )


def test_default_local_user_creation_is_idempotent(session):
    first = get_or_create_local_user()
    second = get_or_create_local_user()

    assert first.id == second.id
    assert first.email == "local@iris.local"
    assert session.query(User).count() == 1


def test_user_document_mapping_is_unique_per_user_document(session):
    user = get_or_create_local_user()
    document = add_doc(session, "Software Essay", "software engineering notes")

    first = get_or_create_user_document_mapping(user, document)
    second = get_or_create_user_document_mapping(user, document)

    assert first.id == second.id
    assert session.query(UserDocumentMapping).count() == 1


def test_tag_namespace_and_document_assignment_are_unique(session):
    user = get_or_create_local_user()
    document = add_doc(
        session, "Epistemology Essay", "thinking and epistemology", ["epistemology"]
    )
    system_tag = get_or_create_tag("Epistemology", scope=TagScope.SYSTEM)
    user_tag = get_or_create_tag("Epistemology", scope=TagScope.USER, user=user)

    assert system_tag.id != user_tag.id
    assert system_tag.namespace == SYSTEM_NAMESPACE
    assert user_tag.namespace == f"user:{user.id}"

    first = tag_document(document, system_tag)
    second = tag_document(document, system_tag)

    assert first.id == second.id
    assert session.query(DocumentTag).count() == 1

    duplicate = Tag(
        scope=TagScope.SYSTEM,
        namespace=SYSTEM_NAMESPACE,
        name="Epistemology",
        slug="epistemology",
    )
    session.add(duplicate)
    with pytest.raises(IntegrityError):
        session.flush()


def test_backfill_system_tags_from_topics(session):
    document = add_doc(
        session, "Stats Essay", "statistics and science", ["statistics", "science"]
    )

    created = backfill_system_tags_from_topics()

    assert created == 2
    tags = {tag.slug for tag in session.query(Tag).all()}
    assert tags == {"statistics", "science"}
    assignments = session.query(DocumentTag).filter_by(document_id=document.id).all()
    assert len(assignments) == 2
    assert {assignment.assignment_namespace for assignment in assignments} == {
        SYSTEM_NAMESPACE
    }


def test_category_backfill_is_deterministic_and_leaves_unknowns(session):
    science = add_doc(
        session,
        "Statistics Essay",
        "statistics and neuroscience research",
        ["statistics"],
    )
    ambiguous = add_doc(session, "Untitled Note", "miscellaneous observations", [])

    assert classify_document_category(science) == DocumentCategory.SCIENCE
    changed = backfill_document_categories()

    assert changed == 1
    assert science.category == DocumentCategory.SCIENCE
    assert ambiguous.category == DocumentCategory.UNKNOWN


def test_system_categories_seed_as_one_word_slugs(session):
    count = seed_default_categories()

    assert count >= 18
    slugs = {category.slug for category in session.query(Category).all()}
    assert {"ai", "software", "money", "philanthropy", "personal"}.issubset(slugs)
    assert all("-" not in slug for slug in slugs)


def test_document_category_assignment_tracks_primary_category(session):
    document = add_doc(
        session,
        "Money Essay",
        "monetary policy and central banking",
        ["monetary policy"],
    )
    money = get_or_create_category("money")
    philosophy = get_or_create_category("philosophy")

    first = assign_category(document, money)
    second = assign_category(document, money)
    third = assign_category(document, philosophy)

    assert first.id == second.id
    assert session.query(DocumentCategoryAssignment).count() == 2
    assert second.is_primary == 0
    assert third.is_primary == 1
