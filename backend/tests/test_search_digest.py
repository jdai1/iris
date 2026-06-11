from iris.digest import get_digest, record_feedback
from iris.embedding import dumps_embedding, embed_text
from iris.models import Document
from iris.repository import get_or_create_source, upsert_document
from iris.search import search_documents


def add_doc(session, source, title, text):
    return upsert_document(
        session,
        source=source,
        url=f"https://{source.canonical_domain}/{title.lower().replace(' ', '-')}",
        final_url=f"https://{source.canonical_domain}/{title.lower().replace(' ', '-')}",
        document_type="essay",
        crawl_status="fetched",
        title=title,
        author="Test Author",
        published_at=None,
        extracted_text=text,
        summary=text[:240],
        topics=["teams", "software"],
        embedding=dumps_embedding(embed_text(text)),
        quality_score=0.8,
        content_hash=title,
    )


def test_search_ranks_relevant_documents(session):
    source = get_or_create_source(session, "https://a.test", status="indexed")
    add_doc(session, source, "Small teams", "small teams coordination costs software organizations")
    add_doc(session, source, "Cooking", "recipes fermentation kitchen vegetables")
    _search, results = search_documents(session, "why are small teams effective", limit=2)
    assert results
    assert results[0].document.title == "Small teams"


def test_digest_uses_feedback_and_excludes_dismissed(session):
    source = get_or_create_source(session, "https://a.test", status="indexed")
    liked = add_doc(session, source, "Software teams", "software teams coordination learning feedback loops")
    dismissed = add_doc(session, source, "Kitchen notes", "recipes kitchen vegetables fermentation")
    record_feedback(session, document_id=liked.id, surface="document", action="save")
    record_feedback(session, document_id=dismissed.id, surface="digest", action="dismiss")
    items = get_digest(session, limit=10)
    assert all(item.document_id != dismissed.id for item in items)
    assert session.query(Document).count() == 2
