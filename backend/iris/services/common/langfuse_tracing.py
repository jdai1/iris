from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from langfuse import get_client as get_langfuse_client
from langfuse import propagate_attributes
from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor

from iris.schemas.retrieval import AgentToolRun, RankedDocument

_OPENAI_AGENTS_INSTRUMENTED = False


def langfuse_enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def agent_conversation_session_id(conversation_identifier: int | str) -> str:
    return f"search:{conversation_identifier}"


def agent_user_id(user_id: int) -> str:
    return str(user_id)


def agent_trace_metadata(
    *,
    conversation_id: int,
    conversation_uuid: str,
    user_id: int,
    firebase_uid: str | None = None,
) -> dict[str, object]:
    trace_user_id = agent_user_id(user_id)
    metadata: dict[str, object] = {
        "conversation_id": conversation_id,
        "conversation_uuid": conversation_uuid,
        "iris_user_id": user_id,
        "user_uuid": trace_user_id,
    }
    if firebase_uid:
        metadata["firebase_uid"] = firebase_uid
    return metadata


def instrument_openai_agents() -> None:
    global _OPENAI_AGENTS_INSTRUMENTED
    if _OPENAI_AGENTS_INSTRUMENTED or not langfuse_enabled():
        return
    try:
        OpenAIAgentsInstrumentor().instrument()
        get_langfuse_client()
        _OPENAI_AGENTS_INSTRUMENTED = True
    except Exception:
        return


def flush_langfuse() -> None:
    if not langfuse_enabled():
        return
    try:
        get_langfuse_client().flush()
    except Exception:
        return


def langfuse_tool_rows(rows: list[RankedDocument]) -> list[dict[str, object]]:
    return [
        {
            "document_id": row.document.id,
            "title": row.document.title,
            "source": row.document.source.canonical_domain,
            "url": row.document.url,
            "category": str(row.document.category.value if hasattr(row.document.category, "value") else row.document.category),
            "summary": row.document.summary,
            "topics": row.document.topics or [],
            "score": round(row.score, 4),
            "reason": row.reason,
        }
        for row in rows
    ]


@contextmanager
def agent_search_observation(
    *,
    mode: str,
    message: str,
    conversation_context: str | None,
    agent_input: str,
    instructions: str,
    model: str,
    max_turns: int,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_metadata: Mapping[str, object] | None = None,
) -> Iterator[object | None]:
    if not langfuse_enabled():
        yield None
        return
    try:
        langfuse = get_langfuse_client()
        metadata = dict(trace_metadata or {})
        if session_id:
            metadata.setdefault("session_id", session_id)
        if user_id:
            metadata.setdefault("user_id", user_id)
        attributes_context = propagate_attributes(
            session_id=session_id,
            user_id=user_id,
            metadata=metadata or None,
            trace_name="iris_agent_search",
        )
        observation_context = langfuse.start_as_current_observation(
            as_type="span",
            name="iris_agent_search",
            input={
                "message": message,
                "conversation_context": conversation_context,
                "agent_input": agent_input,
                "instructions": instructions,
                "model": model,
                "max_turns": max_turns,
            },
            metadata={
                "mode": mode,
                "service": "iris-backend",
                **metadata,
            },
        )
    except Exception:
        yield None
        return
    try:
        with attributes_context, observation_context as observation:
            yield observation
    finally:
        flush_langfuse()


def finish_agent_search_observation(
    observation: object | None,
    *,
    answer: str,
    chosen_ids: list[int],
    ranked: list[RankedDocument],
    tool_runs: list[AgentToolRun],
) -> None:
    if observation is None or not langfuse_enabled():
        return
    try:
        observation.update(
            output={
                "answer": answer,
                "chosen_ids": chosen_ids,
                "result_ids": [row.document.id for row in ranked],
                "results": langfuse_tool_rows(ranked),
                "tool_runs": [
                    {
                        "tool": run.tool.value,
                        "query": run.query,
                        "hits": len(run.rows),
                        "results": langfuse_tool_rows(run.rows),
                    }
                    for run in tool_runs
                ],
            },
            metadata={"result_count": len(ranked), "tool_run_count": len(tool_runs)},
        )
    except Exception:
        return
