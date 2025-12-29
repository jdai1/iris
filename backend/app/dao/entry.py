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
