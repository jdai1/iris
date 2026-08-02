from fastapi.testclient import TestClient

from iris.models import AgentConversation, AgentMessage, AgentMessageRole, User
from iris.routes import app
from iris.services.auth import FirebaseIdentity


def test_admin_query_and_user_inspection_are_admin_only(session, monkeypatch):
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

    queries = client.get("/api/admin/queries", headers=admin_headers)
    assert queries.status_code == 200
    assert queries.json()["items"][0]["content"] == "What should I build this weekend?"
    assert queries.json()["items"][0]["answer_preview"] == "Try a tiny personal utility."
    assert queries.json()["items"][0]["step_count"] == 1

    users = client.get("/api/admin/users", params={"q": "reader"}, headers=admin_headers)
    assert users.status_code == 200
    assert users.json()["items"][0]["query_count"] == 1
    assert users.json()["items"][0]["conversation_count"] == 1

    detail = client.get(
        f"/api/admin/conversations/{conversation.uuid}", headers=admin_headers
    )
    assert detail.status_code == 200
    assert detail.json()["email"] == "reader@example.com"
    assert [message["role"] for message in detail.json()["messages"]] == [
        "user",
        "assistant",
    ]
