from __future__ import annotations

from sqlalchemy import desc, exists, or_, select, text

from iris.dao import db
from iris.dao.user_state import get_or_create_local_user
from iris.models import AgentConversation, AgentMessage, AgentMessageRole, AgentSearchResult, User
from iris.schemas.retrieval import AgentChatResult
from iris.services.common.langfuse_tracing import agent_conversation_session_id, agent_trace_metadata, agent_user_id
from iris.services.retrieval.search import agentic_chat


def create_agent_chat(
    message: str,
    *,
    user: User | None = None,
    limit: int | None = None,
    conversation_id: int | None = None,
    conversation_uuid: str | None = None,
) -> tuple[AgentConversation, AgentMessage, AgentMessage, AgentChatResult]:
    """Persist one user turn, one assistant turn, and the assistant's citations."""
    conversation, user_message = start_agent_chat(
        message,
        user=user,
        conversation_id=conversation_id,
        conversation_uuid=conversation_uuid,
    )
    trace_user = conversation.user
    result = agentic_chat(
        message,
        limit=limit,
        session_id=agent_conversation_session_id(conversation.uuid),
        user_id=agent_user_id(trace_user.id),
        trace_metadata=agent_trace_metadata(
            conversation_id=conversation.id,
            conversation_uuid=conversation.uuid,
            user_id=trace_user.id,
            firebase_uid=trace_user.firebase_uid,
        ),
    )
    assistant_message = finish_agent_chat(conversation, result)
    return conversation, user_message, assistant_message, result


def start_agent_chat(
    message: str,
    *,
    user: User | None = None,
    conversation_id: int | None = None,
    conversation_uuid: str | None = None,
) -> tuple[AgentConversation, AgentMessage]:
    """Persist the user side of an agent chat turn."""
    session = db.current_session()
    user = user or get_or_create_local_user()
    conversation = _get_or_create_conversation(user.id, message, conversation_id, conversation_uuid)
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


def list_agent_conversations(
    limit: int = 30,
    offset: int = 0,
    q: str | None = None,
    *,
    user: User | None = None,
) -> list[AgentConversation]:
    session = db.current_session()
    user = user or get_or_create_local_user()
    page_limit = max(1, min(limit, 100))
    page_offset = max(offset, 0)
    normalized_query = " ".join((q or "").split())
    if normalized_query and session.bind and session.bind.dialect.name == "postgresql":
        rows = session.execute(
            text(
                """
                SELECT c.id
                FROM agent_conversations c
                WHERE c.user_id = :user_id
                  AND to_tsvector('simple', coalesce(c.title, '') || ' ' || coalesce((
                    SELECT string_agg(m.content, ' ')
                    FROM agent_messages m
                    WHERE m.conversation_id = c.id
                  ), '')) @@ websearch_to_tsquery('simple', :q)
                ORDER BY c.updated_at DESC, c.id DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {"user_id": user.id, "q": normalized_query, "limit": page_limit, "offset": page_offset},
        ).all()
        ids = [row.id for row in rows]
        if not ids:
            return []
        conversations = session.execute(select(AgentConversation).where(AgentConversation.id.in_(ids))).scalars().all()
        by_id = {conversation.id: conversation for conversation in conversations}
        return [by_id[id_] for id_ in ids if id_ in by_id]

    query = select(AgentConversation).where(AgentConversation.user_id == user.id)
    if normalized_query:
        pattern = f"%{normalized_query.lower()}%"
        query = query.where(
            or_(
                AgentConversation.title.ilike(pattern),
                exists()
                .where(AgentMessage.conversation_id == AgentConversation.id)
                .where(AgentMessage.content.ilike(pattern)),
            )
        )
    conversations = list(
        session.execute(
            query
            .order_by(desc(AgentConversation.updated_at), desc(AgentConversation.id))
            .limit(page_limit)
            .offset(page_offset)
        ).scalars()
    )
    return conversations


def get_agent_conversation(conversation_id: int, *, user: User | None = None) -> AgentConversation | None:
    session = db.current_session()
    user = user or get_or_create_local_user()
    return session.execute(
        select(AgentConversation).where(
            AgentConversation.id == conversation_id,
            AgentConversation.user_id == user.id,
        )
    ).scalar_one_or_none()


def get_agent_conversation_by_uuid(conversation_uuid: str, *, user: User | None = None) -> AgentConversation | None:
    session = db.current_session()
    user = user or get_or_create_local_user()
    return session.execute(
        select(AgentConversation).where(
            AgentConversation.uuid == conversation_uuid,
            AgentConversation.user_id == user.id,
        )
    ).scalar_one_or_none()


def _get_or_create_conversation(
    user_id: int,
    message: str,
    conversation_id: int | None,
    conversation_uuid: str | None,
) -> AgentConversation:
    session = db.current_session()
    if conversation_uuid:
        conversation = session.execute(
            select(AgentConversation).where(
                AgentConversation.uuid == conversation_uuid,
                AgentConversation.user_id == user_id,
            )
        ).scalar_one_or_none()
        if conversation:
            return conversation

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


def _enum_value(value):
    return value.value if hasattr(value, "value") else value
