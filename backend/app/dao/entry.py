import db
from models.models import Entry


def create_entry(entry: Entry) -> Entry:
    """Create an entry in the database."""
    db.session.add(entry)
    db.session.flush()
    return entry


def create_entries_batch(entries: list[Entry]) -> list[Entry]:
    """Batch create entries in the database."""
    db.session.add_all(entries)
    db.session.flush()
    return entries
