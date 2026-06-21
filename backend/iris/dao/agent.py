from __future__ import annotations

from sqlalchemy import desc, select

from iris.dao import db
from iris.dao.user_state import get_or_create_local_user
from iris.models import AgentConversation, AgentMessage, AgentMessageRole, AgentSearchResult, User
from iris.schemas.retrieval import AgentChatResult
from iris.services.retrieval.search import agentic_chat


def create_agent_chat(
    message: str,
    *,
    user: User | None = None,
    limit: int | None = None,
    conversation_id: int | None = None,
) -> tuple[AgentConversation, AgentMessage, AgentMessage, AgentChatResult]:
    """Persist one user turn, one assistant turn, and the assistant's citations."""
    conversation, user_message = start_agent_chat(message, user=user, conversation_id=conversation_id)
    result = agentic_chat(message, limit=limit)
    assistant_message = finish_agent_chat(conversation, result)
    return conversation, user_message, assistant_message, result


def start_agent_chat(
    message: str,
    *,
    user: User | None = None,
    conversation_id: int | None = None,
) -> tuple[AgentConversation, AgentMessage]:
    """Persist the user side of an agent chat turn."""
    session = db.current_session()
    user = user or get_or_create_local_user()
    conversation = _get_or_create_conversation(user.id, message, conversation_id)
    user_message = AgentMessage(
        conversation_id=conversation.id,
        role=AgentMessageRole.USER,
        content=message,
    )
    session.add(user_message)
    session.flush()
    return conversation, user_message


def finish_agent_chat(conversation: AgentConversation, result: AgentChatResult) -> AgentMessage:
    """Persist the assistant side of an agent chat turn and its citations."""
    session = db.current_session()
    assistant_message = AgentMessage(
        conversation_id=conversation.id,
        role=AgentMessageRole.ASSISTANT,
        content=result.answer,
        steps=[
            {
                "kind": _enum_value(step.kind),
                "title": step.title,
                "detail": step.detail,
                "tool": _enum_value(step.tool),
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
    return assistant_message


def list_agent_conversations(limit: int = 30, *, user: User | None = None) -> list[AgentConversation]:
    session = db.current_session()
    user = user or get_or_create_local_user()
    conversations = list(
        session.execute(
            select(AgentConversation)
            .where(AgentConversation.user_id == user.id)
            .order_by(desc(AgentConversation.updated_at), desc(AgentConversation.id))
            .limit(max(10, min(limit * 3, 100)))
        ).scalars()
    )
    return [conversation for conversation in conversations if _is_useful_conversation(conversation)][: max(1, min(limit, 100))]


def get_agent_conversation(conversation_id: int, *, user: User | None = None) -> AgentConversation | None:
    session = db.current_session()
    user = user or get_or_create_local_user()
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


def _is_useful_conversation(conversation: AgentConversation) -> bool:
    user_messages = [message for message in conversation.messages if message.role == AgentMessageRole.USER]
    assistant_messages = [message for message in conversation.messages if message.role == AgentMessageRole.ASSISTANT]
    if not user_messages:
        return False
    if len(user_messages) > 1:
        return True
    normalized = " ".join(user_messages[0].content.lower().strip().split())
    if normalized in {"hi", "hello", "hey", "yo", "sup", "thanks", "thank you", "ok", "okay"}:
        return False
    return any(message.results for message in assistant_messages) or len(normalized.split()) >= 3


def _enum_value(value):
    return value.value if hasattr(value, "value") else value
