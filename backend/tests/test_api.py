from fastapi.testclient import TestClient

from iris.api import app
from iris.embedding import dumps_embedding, embed_text
from iris.repository import get_or_create_source, upsert_document


def test_health_and_search_api(session):
    source = get_or_create_source(session, "https://api.test", status="indexed")
    upsert_document(
        session,
        source=source,
        url="https://api.test/small-teams",
        final_url="https://api.test/small-teams",
        document_type="essay",
        crawl_status="fetched",
        title="Small teams",
        author="API Author",
        published_at=None,
        extracted_text="small teams coordination costs and tight feedback loops",
        summary="Small teams reduce coordination costs.",
        topics=["teams", "coordination"],
        embedding=dumps_embedding(embed_text("small teams coordination costs and tight feedback loops")),
        quality_score=0.9,
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
