from fastapi.testclient import TestClient

from iris.models import AgentConversation, AgentMessage, AgentMessageRole, User
from iris.routes import app
from iris.services.auth import FirebaseIdentity


def test_admin_query_and_user_inspection_are_admin_only(session, monkeypatch):
    from iris.dao import bookshelf as bookshelf_dao
    from iris.dao.documents import upsert_document
    from iris.dao.sources import get_or_create_source
    from iris.models import BookshelfCollectionVisibility, BookshelfStatus
    from iris.routes import api as api_routes

    identities = {
        "admin-token": FirebaseIdentity(
            uid="admin-user",
            email="julian.dai@gmail.com",
            display_name="Admin",
        ),
        "reader-token": FirebaseIdentity(
            uid="reader-user",
            email="reader@example.com",
            display_name="Reader",
        ),
    }
    monkeypatch.setattr(api_routes, "verify_firebase_token", lambda token: identities[token])
    client = TestClient(app)
    admin_headers = {"Authorization": "Bearer admin-token"}
    reader_headers = {"Authorization": "Bearer reader-token"}

    assert client.get("/api/me", headers=admin_headers).status_code == 200
    assert client.get("/api/me", headers=reader_headers).status_code == 200
    reader = session.query(User).filter(User.email == "reader@example.com").one()
    source = get_or_create_source("https://reader-library.test", status="indexed")
    document = upsert_document(
        source=source,
        url="https://reader-library.test/saved-essay",
        document_type="essay",
        crawl_status="fetched",
        title="A saved essay",
        author="Reader Author",
        published_at=None,
        extracted_text="A useful saved essay.",
        summary="A useful saved essay.",
        topics=["reading"],
        embedding=None,
        content_hash="reader-library-test",
    )
    bookshelf_dao.update_entry(
        reader,
        document,
        status=BookshelfStatus.SAVED,
        favorited=True,
        note="Return to this idea.",
        update_note=True,
    )
    collection = bookshelf_dao.create_collection(
        reader,
        name="Project references",
        description="Useful things to revisit",
        visibility=BookshelfCollectionVisibility.PRIVATE,
    )
    bookshelf_dao.add_collection_item(reader, collection.id, document)
    conversation = AgentConversation(user_id=reader.id, title="Weekend project ideas")
    session.add(conversation)
    session.flush()
    session.add_all(
        [
            AgentMessage(
                conversation_id=conversation.id,
                role=AgentMessageRole.USER,
                content="What should I build this weekend?",
            ),
            AgentMessage(
                conversation_id=conversation.id,
                role=AgentMessageRole.ASSISTANT,
                content="Try a tiny personal utility.",
                steps=[{"kind": "tool", "query": "weekend software projects"}],
            ),
        ]
    )
    session.commit()

    assert client.get("/api/admin/queries", headers=reader_headers).status_code == 403
    assert client.get("/api/admin/users", headers=reader_headers).status_code == 403
    assert client.get("/api/admin/sources", headers=reader_headers).status_code == 403
    assert client.get(f"/api/admin/users/{reader.id}/library", headers=reader_headers).status_code == 403

    queries = client.get("/api/admin/queries", headers=admin_headers)
    assert queries.status_code == 200
    assert queries.json()["items"][0]["content"] == "What should I build this weekend?"
    assert queries.json()["items"][0]["answer_preview"] == "Try a tiny personal utility."
    assert queries.json()["items"][0]["step_count"] == 1

    users = client.get("/api/admin/users", params={"q": "reader"}, headers=admin_headers)
    assert users.status_code == 200
    assert users.json()["items"][0]["query_count"] == 1
    assert users.json()["items"][0]["conversation_count"] == 1
    assert users.json()["items"][0]["saved_document_count"] == 1

    library = client.get(
        f"/api/admin/users/{reader.id}/library", headers=admin_headers
    )
    assert library.status_code == 200
    assert library.json()["entries"]["total"] == 1
    assert library.json()["entries"]["items"][0]["document"]["title"] == "A saved essay"
    assert library.json()["entries"]["items"][0]["favorited"] is True
    assert library.json()["entries"]["items"][0]["note"] == "Return to this idea."
    assert library.json()["collections"][0]["name"] == "Project references"
    assert library.json()["collections"][0]["items"][0]["document"]["uuid"] == document.uuid
    assert client.get("/api/admin/users/999999/library", headers=admin_headers).status_code == 404

    detail = client.get(
        f"/api/admin/conversations/{conversation.uuid}", headers=admin_headers
    )
    assert detail.status_code == 200
    assert detail.json()["email"] == "reader@example.com"
    assert [message["role"] for message in detail.json()["messages"]] == [
        "user",
        "assistant",
    ]
