from datetime import datetime, timezone

from iris.dao.user_state import get_or_create_local_user, get_or_create_user_document_mapping
from iris.services.retrieval.digest import get_digest
from iris.services.ingestion.embedding import dumps_embedding, embed_text
from iris.models import Document
from iris.dao.sources import get_or_create_source
from iris.dao.documents import upsert_document
from iris.services.retrieval.search import search_documents


def add_doc(session, source, title, text):
    return upsert_document(
        source=source,
        url=f"https://{source.canonical_domain}/{title.lower().replace(' ', '-')}",
        document_type="essay",
        crawl_status="fetched",
        title=title,
        author="Test Author",
        published_at=None,
        extracted_text=text,
        summary=text[:240],
        topics=["teams", "software"],
        embedding=dumps_embedding(embed_text(text)),
        content_hash=title,
    )


def test_search_ranks_relevant_documents(session):
    source = get_or_create_source("https://a.test", status="indexed")
    add_doc(session, source, "Small teams", "small teams coordination costs software organizations")
    add_doc(session, source, "Cooking", "recipes fermentation kitchen vegetables")
    _search, results = search_documents("why are small teams effective", limit=2)
    assert results
    assert results[0].document.title == "Small teams"


def test_digest_excludes_dismissed_user_document_mappings(session):
    source = get_or_create_source("https://a.test", status="indexed")
    dismissed = add_doc(session, source, "Kitchen notes", "recipes kitchen vegetables fermentation")
    add_doc(session, source, "Software teams", "software teams coordination learning feedback loops")
    user = get_or_create_local_user()
    mapping = get_or_create_user_document_mapping(user, dismissed)
    mapping.dismissed_at = datetime.now(timezone.utc)

    items = get_digest(limit=10)
    assert all(item.document.id != dismissed.id for item in items)
    assert session.query(Document).count() == 2
