from datetime import datetime, timedelta, timezone

from uuid import UUID

from fastapi.testclient import TestClient

from iris.models import CrawlJob, IndexRun
from iris.routes import app
from iris.services.auth import FirebaseIdentity
from iris.services.ingestion.embedding import dumps_embedding, embed_text
from iris.dao.sources import get_or_create_source
from iris.dao.documents import upsert_document
from iris.dao.links import upsert_link


def _bookshelf_auth(monkeypatch):
    from iris.routes import api as api_routes

    monkeypatch.setattr(
        api_routes,
        "verify_firebase_token",
        lambda token: FirebaseIdentity(uid="bookshelf-user", email="bookshelf@example.com", display_name="Bookshelf User"),
    )
    return {"Authorization": "Bearer bookshelf-token"}


def test_health_and_search_api(session):
    source = get_or_create_source("https://api.test", status="indexed")
    upsert_document(
        source=source,
        url="https://api.test/small-teams",
        document_type="essay",
        crawl_status="fetched",
        title="Small teams",
        author="API Author",
        published_at=None,
        extracted_text="small teams coordination costs and tight feedback loops",
        summary="Small teams reduce coordination costs.",
        topics=["teams", "coordination"],
        embedding=dumps_embedding(embed_text("small teams coordination costs and tight feedback loops")),
        content_hash="api-test",
    )
    session.commit()

    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["documents"] == 1

    search = client.get("/api/search", params={"q": "small teams"})
    assert search.status_code == 200
    body = search.json()
    assert body["results"][0]["document"]["title"] == "Small teams"


def test_document_picker_search_returns_documents_without_answer(session):
    source = get_or_create_source("https://picker.test", status="indexed")
    upsert_document(
        source=source,
        url="https://picker.test/document",
        document_type="essay",
        crawl_status="fetched",
        title="Database search notes",
        author="Picker Author",
        published_at=None,
        extracted_text="full text search for fast collection document picking",
        summary="Fast collection picking with SQL text search.",
        topics=["search"],
        embedding=None,
        content_hash="picker-search",
    )
    session.commit()

    response = TestClient(app).get("/api/documents/search", params={"q": "collection picking", "limit": 5})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == ""
    assert body["results"][0]["document"]["title"] == "Database search notes"


def test_document_detail_uses_uuid_and_exposes_reference_uuids(session):
    source = get_or_create_source("https://document-uuid.test", status="indexed")
    referring = upsert_document(
        source=source, url="https://document-uuid.test/referring", document_type="essay", crawl_status="fetched",
        title="Referring", author=None, published_at=None, extracted_text="referring", summary="Referring.",
        topics=[], embedding=None, content_hash="uuid-referring",
    )
    target = upsert_document(
        source=source, url="https://document-uuid.test/target", document_type="essay", crawl_status="fetched",
        title="Target", author=None, published_at=None, extracted_text="target", summary="Target.",
        topics=[], embedding=None, content_hash="uuid-target",
    )
    upsert_link(source_document=referring, target_url=target.url, anchor_text="target", context="A citation")
    session.commit()

    client = TestClient(app)
    response = client.get(f"/api/documents/{referring.uuid}")
    assert response.status_code == 200
    assert response.json()["outgoing_links"][0]["target_document_uuid"] == target.uuid

    incoming = client.get(f"/api/documents/{target.uuid}")
    assert incoming.status_code == 200
    assert incoming.json()["incoming_links"][0]["source_document_uuid"] == referring.uuid

    legacy = client.get(f"/api/documents/{target.id}")
    assert legacy.status_code == 200
    assert legacy.json()["uuid"] == target.uuid
    assert client.get("/api/documents/not-a-document").status_code == 404

    graph = client.get("/api/graph", params={"mode": "documents", "document_uuid": target.uuid})
    assert graph.status_code == 200
    assert {node["id"] for node in graph.json()["nodes"]} == {f"doc:{referring.uuid}", f"doc:{target.uuid}"}
    assert graph.json()["edges"][0]["source"] == f"doc:{referring.uuid}"
    assert graph.json()["edges"][0]["target"] == f"doc:{target.uuid}"
    assert client.get("/api/graph", params={"mode": "documents", "document_uuid": "missing"}).status_code == 404


def test_huge_numeric_document_uuid_returns_404_for_public_endpoints(session, monkeypatch):
    client = TestClient(app)
    headers = _bookshelf_auth(monkeypatch)
    huge_uuid = "9" * 5000
    collection = client.post(
        "/api/bookshelf/collections",
        json={"name": "UUID bounds", "visibility": "private"},
        headers=headers,
    ).json()

    assert client.get(f"/api/documents/{huge_uuid}").status_code == 404
    assert client.patch(f"/api/documents/{huge_uuid}/bookshelf", json={"status": "saved"}, headers=headers).status_code == 404
    assert client.get("/api/graph", params={"mode": "documents", "document_uuid": huge_uuid}).status_code == 404
    assert client.post(
        f"/api/bookshelf/collections/{collection['id']}/items",
        json={"document_uuid": huge_uuid},
        headers=headers,
    ).status_code == 404
    assert client.delete(
        f"/api/bookshelf/collections/{collection['id']}/items/{huge_uuid}",
        headers=headers,
    ).status_code == 404


def test_directory_sources_default_to_most_referenced(session):
    alpha = get_or_create_source("https://alpha.test", status="indexed")
    beta = get_or_create_source("https://beta.test", status="indexed")
    gamma = get_or_create_source("https://gamma.test", status="indexed")
    alpha_doc = upsert_document(
        source=alpha,
        url="https://alpha.test/essay",
        document_type="essay",
        crawl_status="fetched",
        title="Alpha",
        author=None,
        published_at=None,
        extracted_text="alpha",
        summary=None,
        topics=[],
        embedding=None,
        content_hash="directory-alpha",
    )
    beta_doc = upsert_document(
        source=beta,
        url="https://beta.test/essay",
        document_type="essay",
        crawl_status="fetched",
        title="Beta",
        author=None,
        published_at=None,
        extracted_text="beta",
        summary=None,
        topics=[],
        embedding=None,
        content_hash="directory-beta",
    )
    gamma_doc = upsert_document(
        source=gamma,
        url="https://gamma.test/essay",
        document_type="essay",
        crawl_status="fetched",
        title="Gamma",
        author=None,
        published_at=None,
        extracted_text="gamma",
        summary=None,
        topics=[],
        embedding=None,
        content_hash="directory-gamma",
    )
    upsert_link(source_document=alpha_doc, target_url="https://beta.test/profile", anchor_text="beta", context=None)
    upsert_link(source_document=gamma_doc, target_url="https://beta.test/about", anchor_text="beta", context=None)
    upsert_link(source_document=beta_doc, target_url=alpha_doc.url, anchor_text="alpha", context=None)
    session.commit()

    response = TestClient(app).get("/api/directory/sources")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["items"][0]["canonical_domain"] == "beta.test"
    assert body["items"][0]["inbound_count"] == 2
    assert body["items"][0]["essay_count"] == 1
    assert body["items"][0]["essay_reference_count"] == 1
    assert body["items"][0]["external_source_count"] == 1


def test_me_maps_firebase_identity_to_user(session, monkeypatch):
    from iris.routes import api as api_routes

    monkeypatch.setattr(
        api_routes,
        "verify_firebase_token",
        lambda token: FirebaseIdentity(
            uid="firebase-user-1",
            email="jane@example.com",
            display_name="Jane Example",
            photo_url="https://example.com/jane.png",
        ),
    )

    client = TestClient(app)
    response = client.get("/api/me", headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 200
    body = response.json()
    assert body["firebase_uid"] == "firebase-user-1"
    assert body["email"] == "jane@example.com"
    assert body["display_name"] == "Jane Example"


def test_agent_chat_persists_conversation_and_results(session, monkeypatch):
    from iris.dao import agent as agent_dao
    from iris.routes import api as api_routes
    from iris.schemas.enums import AgentStepKind
    from iris.schemas.retrieval import AgentChatResult, AgentStep, RankedDocument

    source = get_or_create_source("https://agent.test", status="indexed")
    document = upsert_document(
        source=source,
        url="https://agent.test/career",
        document_type="essay",
        crawl_status="fetched",
        title="Choosing a company",
        author="Agent Author",
        published_at=None,
        extracted_text="evaluate job offers company stage manager quality compensation learning trajectory",
        summary="How to evaluate job offers and company fit.",
        topics=["career", "jobs", "companies"],
        embedding=dumps_embedding(embed_text("evaluate job offers company stage manager quality compensation learning trajectory")),
        content_hash="agent-career",
    )
    session.commit()

    session_ids: list[str | None] = []
    user_ids: list[str | None] = []
    trace_metadata_values: list[dict[str, object] | None] = []

    def fake_agentic_chat(
        message: str,
        limit: int = 12,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_metadata: dict[str, object] | None = None,
    ) -> AgentChatResult:
        session_ids.append(session_id)
        user_ids.append(user_id)
        trace_metadata_values.append(trace_metadata)
        return AgentChatResult(
            answer="Use the cited result.",
            results=[RankedDocument(document=document, score=1.0, reason="test sdk result")],
            steps=[
                AgentStep(kind=AgentStepKind.PLAN, title="Run OpenAI agent loop", detail="test"),
                AgentStep(kind=AgentStepKind.TOOL, title="Run semantic", detail="test", tool="semantic", query=message, hits=1),
                AgentStep(kind=AgentStepKind.ANSWER, title="Agent final answer", detail="test"),
            ],
        )

    monkeypatch.setattr(agent_dao, "agentic_chat", fake_agentic_chat)
    monkeypatch.setattr(
        api_routes,
        "verify_firebase_token",
        lambda token: FirebaseIdentity(uid="agent-user", email="agent@example.com", display_name="Agent User"),
    )
    headers = {"Authorization": "Bearer agent-token"}

    client = TestClient(app)
    first = client.post(
        "/api/agent-chat",
        json={"message": "how should I evaluate joining a company?", "limit": 5},
        headers=headers,
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["conversation_id"] > 0
    conversation_uuid = str(UUID(first_body["conversation_uuid"]))
    assert first_body["assistant_message_id"] > first_body["user_message_id"]
    assert first_body["results"][0]["document"]["title"] == "Choosing a company"
    assert str(UUID(first_body["results"][0]["document"]["uuid"]))
    assert {step["kind"] for step in first_body["steps"]} >= {"plan", "tool", "answer"}

    second = client.post(
        "/api/agent-chat",
        json={
            "message": "what about learning trajectory?",
            "limit": 5,
            "conversation_uuid": first_body["conversation_uuid"],
        },
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == first_body["conversation_id"]
    assert second.json()["conversation_uuid"] == first_body["conversation_uuid"]
    assert session_ids == [
        f"search:{conversation_uuid}",
        f"search:{conversation_uuid}",
    ]
    assert trace_metadata_values[0] is not None
    assert user_ids == [str(trace_metadata_values[0]["iris_user_id"]), str(trace_metadata_values[0]["iris_user_id"])]
    assert trace_metadata_values[0]["conversation_id"] == first_body["conversation_id"]
    assert trace_metadata_values[0]["conversation_uuid"] == first_body["conversation_uuid"]
    assert trace_metadata_values[0]["user_uuid"] == str(trace_metadata_values[0]["iris_user_id"])
    assert trace_metadata_values[0]["firebase_uid"] == "agent-user"

    conversations = client.get("/api/agent-conversations", headers=headers)
    assert conversations.status_code == 200
    assert conversations.json()[0]["id"] == first_body["conversation_id"]
    assert conversations.json()[0]["uuid"] == first_body["conversation_uuid"]
    assert conversations.json()[0]["message_count"] == 4

    replay = client.get(f"/api/agent-conversations/{first_body['conversation_uuid']}", headers=headers)
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["id"] == first_body["conversation_id"]
    assert replay_body["uuid"] == first_body["conversation_uuid"]
    assert [message["role"] for message in replay_body["messages"]] == ["user", "assistant", "user", "assistant"]
    assert replay_body["messages"][1]["results"][0]["document"]["title"] == "Choosing a company"


def test_agent_conversations_are_scoped_to_firebase_user(session, monkeypatch):
    from iris.dao import agent as agent_dao
    from iris.routes import api as api_routes
    from iris.schemas.enums import AgentStepKind
    from iris.schemas.retrieval import AgentChatResult, AgentStep, RankedDocument

    source = get_or_create_source("https://scoped.test", status="indexed")
    document = upsert_document(
        source=source,
        url="https://scoped.test/doc",
        document_type="essay",
        crawl_status="fetched",
        title="Scoped result",
        author=None,
        published_at=None,
        extracted_text="scoped auth result",
        summary="Scoped auth result.",
        topics=["auth"],
        embedding=dumps_embedding(embed_text("scoped auth result")),
        content_hash="scoped-auth-result",
    )
    session.commit()

    def fake_verify(token: str) -> FirebaseIdentity:
        return FirebaseIdentity(uid=token, email=f"{token}@example.com", display_name=token)

    def fake_agentic_chat(
        message: str,
        limit: int = 12,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_metadata: dict[str, object] | None = None,
    ) -> AgentChatResult:
        return AgentChatResult(
            answer="Scoped answer.",
            results=[RankedDocument(document=document, score=1.0, reason="scoped")],
            steps=[AgentStep(kind=AgentStepKind.TOOL, title="Run semantic", detail="test", tool="semantic", query=message, hits=1)],
        )

    monkeypatch.setattr(api_routes, "verify_firebase_token", fake_verify)
    monkeypatch.setattr(agent_dao, "agentic_chat", fake_agentic_chat)

    client = TestClient(app)
    first = client.post(
        "/api/agent-chat",
        json={"message": "first user question"},
        headers={"Authorization": "Bearer user-one"},
    )
    assert first.status_code == 200

    second = client.get(
        "/api/agent-conversations",
        headers={"Authorization": "Bearer user-two"},
    )
    assert second.status_code == 200
    assert second.json() == []

    first_history = client.get(
        "/api/agent-conversations",
        headers={"Authorization": "Bearer user-one"},
    )
    assert first_history.status_code == 200
    assert first_history.json()[0]["id"] == first.json()["conversation_id"]
    assert first_history.json()[0]["uuid"] == first.json()["conversation_uuid"]


def test_embedding_map_api_projects_embedded_documents(session):
    source = get_or_create_source("https://map.test", status="indexed")
    for index, text in enumerate(["systems design", "personal knowledge", "search ranking"], start=1):
        upsert_document(
            source=source,
            url=f"https://map.test/doc-{index}",
            document_type="essay",
            crawl_status="fetched",
            title=f"Map doc {index}",
            author=None,
            published_at=None,
            extracted_text=text,
            summary=text,
            topics=["map"],
            embedding=dumps_embedding(embed_text(text)),
            content_hash=f"map-test-{index}",
        )
    session.commit()

    client = TestClient(app)
    response = client.get("/api/embedding-map", params={"limit": 10})

    assert response.status_code == 200
    body = response.json()
    assert body["total_embedded"] == 3
    assert body["dimensions"] > 0
    assert {point["document"]["title"] for point in body["points"]} == {"Map doc 1", "Map doc 2", "Map doc 3"}
    assert all({"x", "y", "z"}.issubset(point) for point in body["points"])


def test_bookshelf_link_api_captures_external_url_with_notes_and_tags(session):
    client = TestClient(app)

    response = client.post(
        "/api/bookshelf/links",
        json={
            "url": "https://example.com/post?utm_source=noise",
            "title": "A saved post",
            "intent_note": "Useful for a writing project.",
            "note": "Initial reflection.",
            "tags": ["writing", "reflection"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["document"]["url"] == "https://example.com/post"
    assert body["document"]["title"] == "A saved post"
    assert body["status"] == "saved"
    assert body["intent_note"] == "Useful for a writing project."
    assert body["note"] == "Initial reflection."
    assert body["tags"] == ["reflection", "writing"]

    list_response = client.get("/api/bookshelf", params={"status": "saved"})
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1


def test_bookshelf_collection_share_includes_notes_and_tags(session, monkeypatch):
    source = get_or_create_source("https://bookshelf.test", status="indexed")
    document = upsert_document(
        source=source,
        url="https://bookshelf.test/essay",
        document_type="essay",
        crawl_status="fetched",
        title="Reflective reading",
        author=None,
        published_at=None,
        extracted_text="reading writing reflection retention",
        summary="Reflection improves retention.",
        topics=["reading"],
        embedding=dumps_embedding(embed_text("reading writing reflection retention")),
        content_hash="bookshelf-share",
    )
    session.commit()
    client = TestClient(app)
    headers = _bookshelf_auth(monkeypatch)

    update = client.patch(
        f"/api/documents/{document.uuid}/bookshelf",
        json={
            "status": "read",
            "note": "Writing made this stick.",
            "tags": ["reading", "memory"],
        },
        headers=headers,
    )
    assert update.status_code == 200

    created = client.post(
        "/api/bookshelf/collections",
        json={
            "name": "Reading better",
            "description": "What helps me retain ideas?",
            "visibility": "share_link",
        },
        headers=headers,
    )
    assert created.status_code == 200
    collection = created.json()
    assert collection["share_token"]

    added = client.post(
        f"/api/bookshelf/collections/{collection['id']}/items",
        json={"document_uuid": document.uuid},
        headers=headers,
    )
    assert added.status_code == 200

    shared = client.get(f"/api/shared/bookshelf/collections/{collection['share_token']}")
    assert shared.status_code == 200
    body = shared.json()
    assert body["name"] == "Reading better"
    assert body["items"][0]["document"]["title"] == "Reflective reading"
    assert body["items"][0]["note"] == "Writing made this stick."
    assert body["items"][0]["tags"] == ["memory", "reading"]

    removed = client.delete(
        f"/api/bookshelf/collections/{collection['id']}/items/{document.uuid}",
        headers=headers,
    )
    assert removed.status_code == 200
    assert removed.json()["items"] == []


def test_delete_bookshelf_collection_removes_collection(session, monkeypatch):
    client = TestClient(app)
    headers = _bookshelf_auth(monkeypatch)
    created = client.post(
        "/api/bookshelf/collections",
        json={"name": "Temporary playlist", "visibility": "private"},
        headers=headers,
    )
    assert created.status_code == 200
    collection_id = created.json()["id"]

    deleted = client.delete(f"/api/bookshelf/collections/{collection_id}", headers=headers)
    assert deleted.status_code == 204

    listed = client.get("/api/bookshelf/collections", headers=headers)
    assert listed.status_code == 200
    assert all(collection["id"] != collection_id for collection in listed.json())

    deleted_again = client.delete(f"/api/bookshelf/collections/{collection_id}", headers=headers)
    assert deleted_again.status_code == 404


def test_bookshelf_collection_names_are_unique_per_user(session, monkeypatch):
    client = TestClient(app)
    headers = _bookshelf_auth(monkeypatch)
    created = client.post(
        "/api/bookshelf/collections",
        json={"name": "Reading queue", "visibility": "private"},
        headers=headers,
    )
    assert created.status_code == 200

    duplicate = client.post(
        "/api/bookshelf/collections",
        json={"name": " reading queue ", "visibility": "private"},
        headers=headers,
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "Collection name already exists"


def test_bookshelf_collection_rename_cannot_collide(session, monkeypatch):
    client = TestClient(app)
    headers = _bookshelf_auth(monkeypatch)
    first = client.post(
        "/api/bookshelf/collections",
        json={"name": "Essays", "visibility": "private"},
        headers=headers,
    )
    second = client.post(
        "/api/bookshelf/collections",
        json={"name": "Papers", "visibility": "private"},
        headers=headers,
    )
    assert first.status_code == 200
    assert second.status_code == 200

    rename = client.patch(
        f"/api/bookshelf/collections/{second.json()['id']}",
        json={"name": "essays"},
        headers=headers,
    )
    assert rename.status_code == 400
    assert rename.json()["detail"] == "Collection name already exists"


def test_documents_api_can_scope_to_crawl_job_and_index_run(session):
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    run = IndexRun(status="succeeded", started_at=started, finished_at=started + timedelta(hours=3))
    source_one = get_or_create_source("https://job-docs-one.test", status="indexed")
    source_two = get_or_create_source("https://job-docs-two.test", status="indexed")
    session.add(run)
    session.flush()
    job_one = CrawlJob(
        source_id=source_one.id,
        index_run_id=run.id,
        started_at=started,
        finished_at=started + timedelta(hours=1),
        status="succeeded",
        documents_indexed=1,
    )
    job_two = CrawlJob(
        source_id=source_two.id,
        index_run_id=run.id,
        started_at=started + timedelta(hours=1),
        finished_at=started + timedelta(hours=2),
        status="succeeded",
        documents_indexed=1,
    )
    session.add_all([job_one, job_two])
    session.flush()
    doc_one = upsert_document(
        source=source_one,
        crawl_job_id=job_one.id,
        url="https://job-docs-one.test/inside-job-one",
        document_type="essay",
        crawl_status="fetched",
        title="Inside job one",
        author=None,
        published_at=None,
        extracted_text="inside job one",
        summary="Inside job one.",
        topics=["jobs"],
        embedding=None,
        content_hash="inside-job-one",
    )
    doc_two = upsert_document(
        source=source_two,
        crawl_job_id=job_two.id,
        url="https://job-docs-two.test/inside-job-two",
        document_type="essay",
        crawl_status="fetched",
        title="Inside job two",
        author=None,
        published_at=None,
        extracted_text="inside job two",
        summary="Inside job two.",
        topics=["jobs"],
        embedding=None,
        content_hash="inside-job-two",
    )
    outside_doc = upsert_document(
        source=source_one,
        url="https://job-docs-one.test/outside-job",
        document_type="essay",
        crawl_status="fetched",
        title="Outside job",
        author=None,
        published_at=None,
        extracted_text="outside job",
        summary="Outside job.",
        topics=["jobs"],
        embedding=None,
        content_hash="outside-job",
    )
    doc_one.last_crawled_at = started + timedelta(minutes=20)
    doc_two.last_crawled_at = started + timedelta(hours=1, minutes=20)
    outside_doc.last_crawled_at = started + timedelta(hours=2, minutes=30)
    session.commit()

    client = TestClient(app)
    job_response = client.get("/api/documents", params={"crawl_job_id": job_one.id})
    run_response = client.get("/api/documents", params={"index_run_id": run.id})

    assert job_response.status_code == 200
    assert [item["title"] for item in job_response.json()["items"]] == ["Inside job one"]
    assert run_response.status_code == 200
    assert {item["title"] for item in run_response.json()["items"]} == {"Inside job one", "Inside job two"}
