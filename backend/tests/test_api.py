from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from iris.models import CrawlJob, IndexRun
from iris.routes import app
from iris.services.ingestion.embedding import dumps_embedding, embed_text
from iris.dao.sources import get_or_create_source
from iris.dao.documents import upsert_document


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

    agentic = client.get("/api/agentic-search", params={"q": "small teams coordination"})
    assert agentic.status_code == 200
    agentic_body = agentic.json()
    assert agentic_body["results"][0]["document"]["title"] == "Small teams"
    assert {tool["tool"] for tool in agentic_body["tools"]} == {"keyword", "semantic", "tags", "categories"}


def test_agent_chat_persists_conversation_and_results(session, monkeypatch):
    from iris.services.retrieval import search as search_service

    monkeypatch.setattr(search_service, "openai_api_key", lambda: None)
    source = get_or_create_source("https://agent.test", status="indexed")
    upsert_document(
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

    client = TestClient(app)
    first = client.post(
        "/api/agent-chat",
        json={"message": "how should I evaluate joining a company?", "limit": 5},
    )
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["conversation_id"] > 0
    assert first_body["assistant_message_id"] > first_body["user_message_id"]
    assert first_body["results"][0]["document"]["title"] == "Choosing a company"
    assert {step["kind"] for step in first_body["steps"]} >= {"plan", "tool", "answer"}

    second = client.post(
        "/api/agent-chat",
        json={
            "message": "what about learning trajectory?",
            "limit": 5,
            "conversation_id": first_body["conversation_id"],
        },
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == first_body["conversation_id"]

    conversations = client.get("/api/agent-conversations")
    assert conversations.status_code == 200
    assert conversations.json()[0]["id"] == first_body["conversation_id"]
    assert conversations.json()[0]["message_count"] == 4

    replay = client.get(f"/api/agent-conversations/{first_body['conversation_id']}")
    assert replay.status_code == 200
    replay_body = replay.json()
    assert [message["role"] for message in replay_body["messages"]] == ["user", "assistant", "user", "assistant"]
    assert replay_body["messages"][1]["results"][0]["document"]["title"] == "Choosing a company"


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


def test_embedding_neighbors_api_uses_full_embeddings(session):
    source = get_or_create_source("https://neighbors.test", status="indexed")
    anchor = upsert_document(
        source=source,
        url="https://neighbors.test/anchor",
        document_type="essay",
        crawl_status="fetched",
        title="Durable software",
        author=None,
        published_at=None,
        extracted_text="durable software infrastructure resilience maintenance stewardship",
        summary="Durable software.",
        topics=["software"],
        embedding=dumps_embedding([1.0, 0.0, 0.0]),
        content_hash="neighbors-anchor",
    )
    upsert_document(
        source=source,
        url="https://neighbors.test/near",
        document_type="essay",
        crawl_status="fetched",
        title="Resilient infrastructure",
        author=None,
        published_at=None,
        extracted_text="resilient software infrastructure maintenance durable systems",
        summary="Resilient infrastructure.",
        topics=["software"],
        embedding=dumps_embedding([0.95, 0.05, 0.0]),
        content_hash="neighbors-near",
    )
    upsert_document(
        source=source,
        url="https://neighbors.test/far",
        document_type="essay",
        crawl_status="fetched",
        title="Cooking notes",
        author=None,
        published_at=None,
        extracted_text="tomato pasta kitchen dinner recipe olive oil",
        summary="Cooking notes.",
        topics=["cooking"],
        embedding=dumps_embedding([-1.0, 0.0, 0.0]),
        content_hash="neighbors-far",
    )
    session.commit()

    client = TestClient(app)
    response = client.get(f"/api/documents/{anchor.id}/embedding-neighbors", params={"limit": 2})

    assert response.status_code == 200
    body = response.json()
    assert [item["document"]["title"] for item in body] == ["Resilient infrastructure", "Cooking notes"]
    assert body[0]["similarity"] > body[1]["similarity"]


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
