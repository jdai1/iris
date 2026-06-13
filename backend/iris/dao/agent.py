from __future__ import annotations

from sqlalchemy import desc, select

from iris.dao import db
from iris.dao.user_state import get_or_create_local_user
from iris.models import AgentConversation, AgentMessage, AgentMessageRole, AgentSearchResult
from iris.services.retrieval.search import AgentChatResult, agentic_chat


def create_agent_chat(
    message: str,
    *,
    limit: int = 12,
    conversation_id: int | None = None,
) -> tuple[AgentConversation, AgentMessage, AgentMessage, AgentChatResult]:
    """Persist one user turn, one assistant turn, and the assistant's citations."""
    session = db.current_session()
    user = get_or_create_local_user()
    conversation = _get_or_create_conversation(user.id, message, conversation_id)

    user_message = AgentMessage(
        conversation_id=conversation.id,
        role=AgentMessageRole.USER,
        content=message,
    )
    session.add(user_message)
    session.flush()

    result = agentic_chat(message, limit=limit)
    assistant_message = AgentMessage(
        conversation_id=conversation.id,
        role=AgentMessageRole.ASSISTANT,
        content=result.answer,
        steps=[
            {
                "kind": step.kind.value,
                "title": step.title,
                "detail": step.detail,
                "tool": step.tool,
                "query": step.query,
                "hits": step.hits,
            }
            for step in result.steps
        ],
    )
    session.add(assistant_message)
    session.flush()

    for rank, item in enumerate(result.results, start=1):
        session.add(
            AgentSearchResult(
                message_id=assistant_message.id,
                document_id=item.document.id,
                rank=rank,
                score=item.score,
                reason=item.reason,
            )
        )

    conversation.updated_at = assistant_message.created_at
    session.flush()
    return conversation, user_message, assistant_message, result


def list_agent_conversations(limit: int = 30) -> list[AgentConversation]:
    session = db.current_session()
    user = get_or_create_local_user()
    return list(
        session.execute(
            select(AgentConversation)
            .where(AgentConversation.user_id == user.id)
            .order_by(desc(AgentConversation.updated_at), desc(AgentConversation.id))
            .limit(max(1, min(limit, 100)))
        ).scalars()
    )


def get_agent_conversation(conversation_id: int) -> AgentConversation | None:
    session = db.current_session()
    user = get_or_create_local_user()
    return session.execute(
        select(AgentConversation).where(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user.id,
        )
    ).scalar_one_or_none()


def _get_or_create_conversation(user_id: int, message: str, conversation_id: int | None) -> AgentConversation:
    session = db.current_session()
    if conversation_id is not None:
        conversation = session.execute(
            select(AgentConversation).where(
                AgentConversation.id == conversation_id,
                AgentConversation.user_id == user_id,
            )
        ).scalar_one_or_none()
        if conversation:
            return conversation

    title = " ".join(message.strip().split())[:120] or "Untitled search"
    conversation = AgentConversation(user_id=user_id, title=title)
    session.add(conversation)
    session.flush()
    return conversation
