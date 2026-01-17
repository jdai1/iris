import uuid

from sqlalchemy import select

import app.db as db
from app.models.models import Entry
from app.schemas.crawl import EntryCreateParams


def create_entry(params: EntryCreateParams) -> Entry:
    """Create an entry in the database."""
    entry = Entry(
        link_id=params.link_id,
        title=params.title,
        summary=params.summary,
        topics=params.topics,
        author=params.author,
        date_published=params.date_published,
        embedding=params.embedding,
    )
    db.session.add(entry)
    db.session.flush()
    return entry


def create_entries_batch(params_list: list[EntryCreateParams]) -> list[Entry]:
    """Batch create entries in the database."""
    entries = [
        Entry(
            link_id=params.link_id,
            title=params.title,
            summary=params.summary,
            topics=params.topics,
            author=params.author,
            date_published=params.date_published,
            embedding=params.embedding,
        )
        for params in params_list
    ]
    db.session.add_all(entries)
    db.session.flush()
    return entries


def get_entries_by_link_ids(link_ids: set[uuid.UUID]) -> list[Entry]:
    """Get entries by link IDs."""
    if not link_ids:
        return []

    stmt = select(Entry).where(Entry.link_id.in_(link_ids))
    result = db.session.execute(stmt)
    return list(result.scalars().all())


def delete_entries_by_link_ids(link_ids: set[uuid.UUID]) -> int:
    """
    Delete entries by link IDs.

    Returns:
        Number of entries deleted
    """
    if not link_ids:
        return 0

    entries = get_entries_by_link_ids(link_ids)
    if not entries:
        return 0

    for entry in entries:
        db.session.delete(entry)
    db.session.flush()
    return len(entries)
