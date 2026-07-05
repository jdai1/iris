from datetime import datetime, timezone

from iris.dao import bookshelf
from iris.dao.user_state import get_or_create_local_user, get_or_create_user_document_mapping
from iris.services.ingestion.embedding import dumps_embedding, embed_text
from iris.models import BookshelfStatus, Document
from iris.dao.sources import get_or_create_source
from iris.dao.documents import upsert_document
from iris.services.common.langfuse_tracing import (
    agent_search_observation,
    finish_agent_search_observation,
    instrument_openai_agents,
)
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


def test_langfuse_trace_noops_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    with agent_search_observation(
        mode="sync",
        message="technical interviews",
        conversation_context=None,
        agent_input="technical interviews",
        instructions="test instructions",
        model="test-model",
        max_turns=1,
        session_id="search:1",
    ) as observation:
        assert observation is None

    finish_agent_search_observation(
        observation,
        answer="No match.",
        chosen_ids=[],
        ranked=[],
        tool_runs=[],
    )


def test_langfuse_openai_agents_instrumentation_noops_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    instrument_openai_agents()


def test_bookshelf_lists_saved_entries_and_excludes_archived(session):
    source = get_or_create_source("https://a.test", status="indexed")
    archived = add_doc(session, source, "Kitchen notes", "recipes kitchen vegetables fermentation")
    saved = add_doc(session, source, "Software teams", "software teams coordination learning feedback loops")
    user = get_or_create_local_user()
    mapping = get_or_create_user_document_mapping(user, archived)
    mapping.dismissed_at = datetime.now(timezone.utc)
    bookshelf.save_document(user, saved)

    items, total = bookshelf.list_entries(user, status=BookshelfStatus.SAVED)
    assert total == 1
    assert [item.document.id for item in items] == [saved.id]
    assert session.query(Document).count() == 2


def test_bookshelf_update_persists_note_favorite_and_tags(session):
    source = get_or_create_source("https://a.test", status="indexed")
    document = add_doc(session, source, "Writing notes", "writing reflection memory attention")
    user = get_or_create_local_user()

    mapping = bookshelf.update_entry(
        user,
        document,
        status=BookshelfStatus.READ,
        favorited=True,
        note="This is worth revisiting.",
        intent_note="Need this for retention.",
        tags=["writing", "reflection", "writing"],
        update_note=True,
        update_intent_note=True,
    )

    tags = bookshelf.user_tags_for_documents(user, [document.id])
    assert mapping.bookshelf_status == BookshelfStatus.READ
    assert mapping.read_at is not None
    assert mapping.favorited_at is not None
    assert mapping.note == "This is worth revisiting."
    assert mapping.intent_note == "Need this for retention."
    assert tags[document.id] == ["reflection", "writing"]
