"""Persistence helpers for system-managed document categories."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select, update

from iris.dao import db
from iris.models import Category, Document, DocumentCategoryAssignment


@dataclass(frozen=True)
class SeedCategory:
    """Definition for one default system category."""

    slug: str
    name: str
    description: str
    color: str


DEFAULT_CATEGORIES: tuple[SeedCategory, ...] = (
    SeedCategory(
        "ai",
        "AI",
        "AI, machine learning, AI safety, LLMs, agents, and AI policy.",
        "#60a5fa",
    ),
    SeedCategory(
        "software",
        "Software",
        "Software engineering, systems, programming, infrastructure, and developer tools.",
        "#38bdf8",
    ),
    SeedCategory(
        "work",
        "Work",
        "Engineering leadership, management, teams, careers, execution, and organizations.",
        "#34d399",
    ),
    SeedCategory(
        "productivity",
        "Productivity",
        "Habits, focus, time management, self-improvement systems, and agency.",
        "#a3e635",
    ),
    SeedCategory(
        "rationality",
        "Rationality",
        "Rationality, epistemics, cognitive biases, psychology, and decision making.",
        "#facc15",
    ),
    SeedCategory(
        "philosophy",
        "Philosophy",
        "Ethics, philosophy of mind, epistemology, moral philosophy, and metaphysics.",
        "#c084fc",
    ),
    SeedCategory(
        "money",
        "Money",
        "Economics, monetary policy, markets, finance, taxes, and investing.",
        "#f59e0b",
    ),
    SeedCategory(
        "philanthropy",
        "Philanthropy",
        "Effective altruism, charity evaluation, global health funding, and giving.",
        "#22c55e",
    ),
    SeedCategory(
        "health",
        "Health",
        "Medicine, public health, mental health, neuroscience, bio, and longevity.",
        "#2dd4bf",
    ),
    SeedCategory(
        "dating",
        "Dating",
        "Dating, relationships, friendship, family, attraction, and social life.",
        "#fb7185",
    ),
    SeedCategory(
        "culture",
        "Culture",
        "Media criticism, books, film, games, internet culture, art, and taste.",
        "#f97316",
    ),
    SeedCategory(
        "politics",
        "Politics",
        "Policy, governance, regulation, geopolitics, law, institutions, and public discourse.",
        "#ef4444",
    ),
    SeedCategory(
        "history",
        "History",
        "History, anthropology, civilization, linguistics, religion and society, and geopolitics.",
        "#a78bfa",
    ),
    SeedCategory(
        "science",
        "Science",
        "Science, math, research practice, physics, biology, statistics, and measurement.",
        "#06b6d4",
    ),
    SeedCategory(
        "personal",
        "Personal",
        "Autobiographical essays, life reflections, identity, college, travel, and personal growth.",
        "#e879f9",
    ),
    SeedCategory(
        "writing",
        "Writing",
        "Blogging, writing practice, note-taking, creativity, publishing, and personal websites.",
        "#84cc16",
    ),
    SeedCategory(
        "fiction",
        "Fiction",
        "Fiction, speculation, fantasy, RPGs, mythology, narrative design, and worldbuilding.",
        "#8b5cf6",
    ),
    SeedCategory(
        "education",
        "Education",
        "Education, college advice, curriculum, self-study, teaching, and learning strategy.",
        "#14b8a6",
    ),
)


def slugify_category(value: str) -> str:
    """Normalize a category label into a one-word slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "unknown"


def seed_default_categories() -> int:
    """Create or refresh the default system category rows."""
    count = 0
    for seed in DEFAULT_CATEGORIES:
        category = get_or_create_category(
            seed.slug,
            name=seed.name,
            description=seed.description,
            color=seed.color,
        )
        if (
            category.name != seed.name
            or category.description != seed.description
            or category.color != seed.color
            or category.status != "active"
        ):
            category.name = seed.name
            category.description = seed.description
            category.color = seed.color
            category.status = "active"
        count += 1
    db.flush()
    return count


def get_or_create_category(
    slug_or_name: str,
    *,
    name: str | None = None,
    description: str | None = None,
    color: str | None = None,
) -> Category:
    """Return a system category by slug, creating it when needed."""
    session = db.current_session()
    slug = slugify_category(slug_or_name)
    category = session.execute(
        select(Category).where(Category.slug == slug)
    ).scalar_one_or_none()
    if category:
        return category
    category = Category(
        slug=slug,
        name=name or slug.title(),
        description=description,
        color=color,
        status="active",
    )
    session.add(category)
    session.flush()
    return category


def assign_category(
    document: Document,
    category: Category,
    *,
    is_primary: bool = True,
    assigned_by: str = "system",
) -> DocumentCategoryAssignment:
    """Assign a system category to a document."""
    session = db.current_session()
    if is_primary:
        session.execute(
            update(DocumentCategoryAssignment)
            .where(DocumentCategoryAssignment.document_id == document.id)
            .where(DocumentCategoryAssignment.is_primary == 1)
            .values(is_primary=0)
        )
    assignment = session.execute(
        select(DocumentCategoryAssignment).where(
            DocumentCategoryAssignment.document_id == document.id,
            DocumentCategoryAssignment.category_id == category.id,
        )
    ).scalar_one_or_none()
    if assignment is None:
        assignment = DocumentCategoryAssignment(
            document_id=document.id,
            category_id=category.id,
        )
        session.add(assignment)
    assignment.is_primary = 1 if is_primary else 0
    assignment.assigned_by = assigned_by
    session.flush()
    return assignment
