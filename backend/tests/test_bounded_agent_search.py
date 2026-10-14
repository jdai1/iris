import asyncio
import json
import sys
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from iris.dao import search as dao
from iris.dao.sources import get_or_create_source
from iris.models import Category, Document, DocumentCategoryAssignment, DocumentTag, Tag
from iris.schemas.enums import DocumentCategory
from iris.schemas.retrieval import AgentSearchOutput
from iris.services.retrieval import search
from sqlalchemy import event
from test_search_bookshelf import add_doc


def test_keyword_search_ranks_before_loading_and_excludes_ineligible(session):
    source = get_or_create_source("https://a.test", status="indexed")
    for i in range(45):
        add_doc(session, source, f"Ordinary {i}", "small teams")
    best = add_doc(session, source, "Best", "small teams coordination")
    best_id = best.id
    bad = add_doc(session, source, "Ineligible", "small teams coordination")
    bad.crawl_status = "pending"
    session.flush()
    session.expunge_all()
    loaded = []
    def record_load(_session, obj):
        if isinstance(obj, Document):
            loaded.append(obj.id)
    event.listen(session, "loaded_as_persistent", record_load)
    try:
        rows = dao.keyword_search_documents({"small", "teams", "coordination"}, limit=2)
    finally:
        event.remove(session, "loaded_as_persistent", record_load)
    assert rows[0].document.id == best_id
    assert rows[0].score == 1.0
    assert len(rows) == len(loaded) == 2
    assert len(dao.keyword_search_documents({"small"}, limit=999)) == 30


def test_tag_and_category_search_include_assignments_and_exact_topics(session):
    source = get_or_create_source("https://a.test", status="indexed")
    topic = add_doc(session, source, "Topic", "example")
    topic.topics = ["Teams"]
    topic.category = DocumentCategory.SOFTWARE
    assigned = add_doc(session, source, "Assigned", "example")
    assigned.topics = None
    partial = add_doc(session, source, "Partial", "example")
    partial.topics = ["teamsmanship"]
    tag = Tag(scope="system", namespace="system", name="Teams", slug="teams")
    category = Category(name="Software", slug="software")
    session.add_all([tag, category])
    session.flush()
    session.add_all([
        DocumentTag(document_id=assigned.id, tag_id=tag.id, assignment_namespace="system"),
        DocumentCategoryAssignment(document_id=assigned.id, category_id=category.id),
    ])
    session.flush()
    assert [row.document.id for row in dao.tag_search_documents({"teams"}, limit=5)] == [assigned.id, topic.id]
    assert [row.document.id for row in dao.category_search_documents({"software"}, limit=5)] == [assigned.id, topic.id]
    assert dao.tag_search_documents(set(), limit=5) == []
    assert dao.category_search_documents(set(), limit=5) == []


def test_sqlite_semantic_search_loads_only_winners(session):
    source = get_or_create_source("https://a.test", status="indexed")
    for i in range(120):
        doc = add_doc(session, source, f"Document {i}", "example")
        doc.embedding_vector = json.dumps([0.0, 1.0])
    winner = add_doc(session, source, "Winner", "example")
    winner.embedding_vector = json.dumps([1.0, 0.0])
    winner_id = winner.id
    session.flush()
    session.expunge_all()
    rows = dao.semantic_search_documents([1.0, 0.0], limit=1)
    assert [row.document.id for row in rows] == [winner_id]
    assert len([obj for obj in session.identity_map.values() if isinstance(obj, Document)]) == 1


def test_source_metadata_does_not_load_all_source_documents(session):
    source = get_or_create_source("https://a.test", status="indexed")
    for i in range(15):
        add_doc(session, source, f"Document {i}", "example")
    session.flush()
    payload = json.loads(search._serialize_source_metadata(source))
    assert len(payload["recent_documents"]) == 10
    assert "documents" not in source.__dict__


@pytest.mark.parametrize("streaming", [False, True])
def test_agent_greeting_never_preloads_corpus(session, monkeypatch, streaming):
    def unexpected_load():
        pytest.fail("agent preloaded the corpus")
    monkeypatch.setattr(dao, "get_searchable_documents", unexpected_load)
    monkeypatch.setattr(search, "instrument_openai_agents", lambda: None)
    monkeypatch.setattr(search, "agent_search_observation", lambda **kwargs: nullcontext(None))
    monkeypatch.setattr(search, "finish_agent_search_observation", lambda *args, **kwargs: None)
    output = AgentSearchOutput(answer="Hello!", document_ids=[])
    class Run:
        final_output = output
        async def stream_events(self):
            if False:
                yield None
    runner = SimpleNamespace(run_sync=lambda *args, **kwargs: Run(), run_streamed=lambda *args, **kwargs: Run())
    monkeypatch.setitem(sys.modules, "agents", SimpleNamespace(
        Agent=lambda **kwargs: kwargs, ModelSettings=lambda **kwargs: kwargs,
        Runner=runner, function_tool=lambda fn: fn,
    ))
    if streaming:
        async def consume():
            return [item async for item in search.stream_openai_agentic_chat("hello")]
        assert asyncio.run(consume())[-1].result.answer == "Hello!"
    else:
        assert search._openai_agentic_chat("hello").answer == "Hello!"
