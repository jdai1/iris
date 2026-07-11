from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping

import httpx
from sqlalchemy import select

from iris.dao import db
from iris.dao import search as search_dao
from iris.services.common.config import (
    AGENT_SEARCH_MAX_TURNS,
    AGENT_SEARCH_MODEL,
    AGENT_SEARCH_REASONING_EFFORT,
    SEARCH_RERANK_MODEL,
    SEARCH_RERANK_TIMEOUT_SECONDS,
    USE_LLM_RERANKER,
    openai_api_key,
)
from iris.services.common.langfuse_tracing import agent_search_observation, finish_agent_search_observation, instrument_openai_agents
from iris.services.ingestion.embedding import cosine, embed_text, loads_embedding
from iris.models import Category, Document, DocumentCategoryAssignment, DocumentTag, Source, Tag
from iris.schemas.enums import AgentStepKind, AgentToolName, DocumentType
from iris.schemas.retrieval import AgentChatResult, AgentChatStreamEvent, AgentSearchOutput, AgentStep, AgentToolRun, RankedDocument

AGENT_RESULT_SAFETY_CAP = 20
AGENT_INSTRUCTIONS = (
    "You are the search intelligence for Iris, a personal corpus search engine for indexed blogs and essays. "
    "You have retrieval tools plus metadata tools: keyword_search, semantic_search, tag_search, category_search, "
    "get_document_metadata, and get_source_metadata. "
    "Do not call retrieval tools for greetings, small talk, vague fragments, or messages where the user's search intent is unclear. "
    "In those cases, answer conversationally and ask one concise clarifying question. "
    "Use the supplied conversation context to resolve follow-ups, references like 'that post', and requests about links you already recommended. "
    "When the current message is a follow-up or instruction to proceed, infer the intended search from the conversation transcript. "
    "Before calling a retrieval tool, rewrite the user's request into a standalone search query in your head. "
    "The tool query must preserve the user's specific subject, domain, and constraints from prior turns. "
    "Do not broaden a specific subject into generic software, technical writing, productivity, or engineering unless the user asks for that broadening. "
    "Treat explicit modifiers, subtypes, roles, audiences, and requested angles as hard constraints, not optional keywords. "
    "Do not substitute a broader category, adjacent workflow, opposite perspective, or different audience just because it shares surface terms. "
    "When a candidate document is only broadly related, inspect its metadata before citing it; title, summary, topics, or excerpt must directly support the requested subtype and angle. "
    "If inspection shows only adjacent or broadly related documents, say the corpus does not appear to contain a good match and return no document_ids. "
    "Use the resolved standalone intent as the tool query, not necessarily the literal latest message. "
    "When recall matters or initial hits are thin or noisy, try 2-4 distinct standalone query formulations before answering. "
    "Keep alternate queries narrow and anchored to the user's intent rather than using generic category searches as filler. "
    "Ask a clarifying question only when the full conversation still does not contain a workable search intent. "
    "If the user asks about a previously recommended document, use its internal ref from context and call get_document_metadata before answering. "
    "Use get_source_metadata when the user asks about a blog/source rather than one post. "
    "When the user gives a clear corpus search request, call at least one retrieval tool before answering. "
    "Use more than one tool or query when it improves recall or disambiguation. "
    "Only cite documents returned by tools. Return document_ids only for documents that are clearly relevant enough to show as link cards. "
    "Document IDs and database IDs are internal handles only: never mention them in answer text, explanations, or user-facing tool summaries. "
    "The UI will show the search results. Your answer should not be the main artifact. "
    "For normal search requests, write one short natural-language summary sentence, at most two sentences. "
    "Briefly describe what the results seem to contain and any important mismatch or caveat. "
    "If the matches are only adjacent, broad, or weak, say that directly: 'I did not find a strong direct match; these are the closest results I found.' "
    "Do not write a checklist, essay, or bullet list of every result. Do not repeat titles unless it is necessary to disambiguate. "
    "When good matches exist, let document_ids carry the results. "
    "Before finalizing, compare the user's exact query against every document_id you are about to return. "
    "Your final document_ids are the relevance filter: selectively remove cards that are adjacent, broader, candidate-oriented, behavioral, generic process, "
    "or about a different subtype than requested, even if those cards appeared high in tool results. "
    "Returning no document_ids is better than showing loosely related or generic cards. "
    "Do not repeat the same document, URL, or duplicate content in document_ids. "
    "Choose the number of document_ids based on relevance; return none when no retrieved document is relevant enough."
)


def _terms(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text)}


def _keyword_score(query_terms: set[str], document: Document) -> float:
    haystack = " ".join(
        item or ""
        for item in (
            document.title,
            document.author,
            document.one_liner,
            document.audience,
            document.summary,
            " ".join(document.takeaways or []),
            " ".join(document.topics or []),
            str(document.category.value if hasattr(document.category, "value") else document.category),
            document.extracted_text[:3000] if document.extracted_text else "",
            document.source.name,
            document.source.canonical_domain,
        )
    ).lower()
    if not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in haystack)
    return hits / len(query_terms)


def _document_search_payload(document: Document) -> dict[str, object]:
    return {
        "document_id": document.id,
        "title": document.title,
        "source": document.source.canonical_domain,
        "url": document.url,
        "category": str(document.category.value if hasattr(document.category, "value") else document.category),
        "summary": document.summary,
        "one_liner": document.one_liner,
        "audience": document.audience,
        "takeaways": document.takeaways or [],
        "topics": document.topics or [],
    }


def search_documents(query: str, limit: int = 12, persist: bool = True) -> tuple[None, list[RankedDocument]]:
    query_vector = embed_text(query)
    query_terms = _terms(query)
    vector_rows = search_dao.vector_search_documents(query_vector, limit=max(limit * 8, 80))
    documents = [document for document, _score in vector_rows] if vector_rows else search_dao.get_searchable_documents()
    vector_scores = {document.id: score for document, score in vector_rows}
    saved_ids = search_dao.get_favorited_document_ids()
    dismissed_ids = search_dao.get_dismissed_document_ids()

    ranked: list[RankedDocument] = []
    for document in documents:
        semantic = vector_scores.get(document.id)
        if semantic is None:
            semantic = cosine(query_vector, loads_embedding(document.embedding_vector))
        keyword = _keyword_score(query_terms, document)
        favorite_bonus = 0.08 if document.id in saved_ids else 0.0
        dismissed_penalty = 0.18 if document.id in dismissed_ids else 0.0
        score = (0.55 * semantic) + (0.45 * keyword) + favorite_bonus - dismissed_penalty
        if score <= 0.03:
            continue
        reason_bits = []
        if keyword > 0:
            reason_bits.append(f"keyword overlap {keyword:.0%}")
        if semantic > 0.12:
            reason_bits.append("semantic match")
        if not reason_bits:
            reason_bits.append("related corpus item")
        ranked.append(RankedDocument(document=document, score=score, reason=", ".join(reason_bits)))

    ranked.sort(key=lambda item: item.score, reverse=True)
    candidate_pool = ranked[: max(limit * 3, 24)]
    candidate_pool = _rerank_candidates(query, candidate_pool)
    ranked = _dedupe_ranked_documents(_expand_with_graph_neighbors(candidate_pool[:limit], limit))

    return None, ranked[:limit]


def agentic_chat(
    message: str,
    limit: int | None = None,
    conversation_context: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_metadata: Mapping[str, object] | None = None,
) -> AgentChatResult:
    """Run the OpenAI Agents SDK retrieval loop."""
    if not openai_api_key():
        raise RuntimeError("OpenAI API key is required for agentic chat")
    return _openai_agentic_chat(
        message,
        limit=limit or AGENT_RESULT_SAFETY_CAP,
        conversation_context=conversation_context,
        session_id=session_id,
        user_id=user_id,
        trace_metadata=trace_metadata,
    )


async def stream_openai_agentic_chat(
    message: str,
    limit: int | None = None,
    conversation_context: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_metadata: Mapping[str, object] | None = None,
):
    """Stream an OpenAI Agents SDK-controlled retrieval loop."""
    instrument_openai_agents()
    from agents import Agent, ModelSettings, Runner, function_tool

    max_result_cards = limit or AGENT_RESULT_SAFETY_CAP
    key = openai_api_key()
    if key:
        os.environ.setdefault("OPENAI_API_KEY", key)

    documents = search_dao.get_searchable_documents()
    documents_by_id = {document.id: document for document in documents}
    tool_runs: list[AgentToolRun] = []
    steps: list[AgentStep] = []

    def serialize_rows(rows: list[RankedDocument]) -> str:
        return json.dumps(
            [
                {
                    **_document_search_payload(row.document),
                    "score": round(row.score, 4),
                    "reason": row.reason,
                }
                for row in rows
            ],
            ensure_ascii=False,
        )

    @function_tool
    def keyword_search(query: str, max_results: int = 12) -> str:
        """Search Iris documents by lexical overlap using a standalone resolved query that preserves the user's specific subject and constraints."""
        rows = _keyword_search(_terms(query), documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool=AgentToolName.KEYWORD, query=query, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def semantic_search(query: str, max_results: int = 12) -> str:
        """Search Iris documents by semantic similarity using a standalone resolved query that preserves the user's specific subject and constraints."""
        rows = _semantic_search(query, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool=AgentToolName.SEMANTIC, query=query, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def tag_search(terms: str, max_results: int = 12) -> str:
        """Search Iris documents by comma-separated topic or tag terms."""
        normalized = {term.strip().lower() for term in terms.split(",") if term.strip()}
        rows = _tag_search(normalized, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool=AgentToolName.TAGS, query=terms, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def category_search(categories: str, max_results: int = 12) -> str:
        """Search Iris documents by comma-separated high-level categories like startups, software, culture, or personal."""
        normalized = {term.strip().lower() for term in categories.split(",") if term.strip()}
        rows = _category_search(normalized, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool=AgentToolName.CATEGORIES, query=categories, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def get_document_metadata(document_id: int) -> str:
        """Fetch metadata and a short excerpt for one Iris document by document_id."""
        document = documents_by_id.get(document_id)
        if document is None:
            tool_runs.append(AgentToolRun(tool=AgentToolName.DOCUMENT_METADATA, query=str(document_id), rows=[]))
            return json.dumps({"error": "document not found", "document_id": document_id})
        tool_runs.append(
            AgentToolRun(
                tool=AgentToolName.DOCUMENT_METADATA,
                query=str(document_id),
                rows=[RankedDocument(document=document, score=1.0, reason="document metadata lookup")],
            )
        )
        return _serialize_document_metadata(document)

    @function_tool
    def get_source_metadata(domain: str) -> str:
        """Fetch metadata about a source/blog by canonical domain."""
        normalized = domain.strip().lower()
        source = db.current_session().scalar(select(Source).where(Source.canonical_domain == normalized))
        tool_runs.append(AgentToolRun(tool=AgentToolName.SOURCE_METADATA, query=normalized, rows=[]))
        if source is None:
            return json.dumps({"error": "source not found", "domain": normalized})
        return _serialize_source_metadata(source)

    agent = Agent(
        name="Iris corpus search agent",
        model=AGENT_SEARCH_MODEL,
        output_type=AgentSearchOutput,
        instructions=AGENT_INSTRUCTIONS,
        model_settings=ModelSettings(tool_choice="auto", reasoning={"effort": AGENT_SEARCH_REASONING_EFFORT}),
        tools=[
            keyword_search,
            semantic_search,
            tag_search,
            category_search,
            get_document_metadata,
            get_source_metadata,
        ],
    )
    agent_input = _agent_input(message, conversation_context)
    with agent_search_observation(
        mode="stream",
        message=message,
        conversation_context=conversation_context,
        agent_input=agent_input,
        instructions=AGENT_INSTRUCTIONS,
        model=AGENT_SEARCH_MODEL,
        max_turns=AGENT_SEARCH_MAX_TURNS,
        session_id=session_id,
        user_id=user_id,
        trace_metadata=trace_metadata,
    ) as langfuse_observation:
        run = Runner.run_streamed(agent, agent_input, max_turns=AGENT_SEARCH_MAX_TURNS)
        emitted_tool_runs = 0
        async for sdk_event in run.stream_events():
            event_name = getattr(sdk_event, "name", "")
            if event_name in {"tool_output", "tool_search_output_created"} and len(tool_runs) > emitted_tool_runs:
                for run_item in tool_runs[emitted_tool_runs:]:
                    step = _tool_step(run_item.tool, run_item.query, run_item.rows)
                    steps.append(step)
                    yield AgentChatStreamEvent(event="tool_result", step=step, rows=run_item.rows)
                emitted_tool_runs = len(tool_runs)

        if len(tool_runs) > emitted_tool_runs:
            for run_item in tool_runs[emitted_tool_runs:]:
                step = _tool_step(run_item.tool, run_item.query, run_item.rows)
                steps.append(step)
                yield AgentChatStreamEvent(event="tool_result", step=step, rows=run_item.rows)

        output = run.final_output
        if isinstance(output, AgentSearchOutput):
            answer = output.answer
            chosen_ids = output.document_ids
        else:
            answer = str(output or "")
            chosen_ids = []

        ranked = _rank_agent_documents(tool_runs, chosen_ids, message, max_result_cards)
        finish_agent_search_observation(
            langfuse_observation,
            answer=answer,
            chosen_ids=chosen_ids,
            ranked=ranked,
            tool_runs=tool_runs,
        )
    yield AgentChatStreamEvent(event="final", result=AgentChatResult(answer=answer, results=ranked, steps=steps))


def _openai_agentic_chat(
    message: str,
    limit: int = AGENT_RESULT_SAFETY_CAP,
    conversation_context: str | None = None,
    session_id: str | None = None,
    user_id: str | None = None,
    trace_metadata: Mapping[str, object] | None = None,
) -> AgentChatResult:
    """Let the OpenAI Agents SDK choose retrieval tools and synthesize a grounded answer."""
    instrument_openai_agents()
    from agents import Agent, ModelSettings, Runner, function_tool

    key = openai_api_key()
    if key:
        os.environ.setdefault("OPENAI_API_KEY", key)

    documents = search_dao.get_searchable_documents()
    documents_by_id = {document.id: document for document in documents}
    tool_runs: list[AgentToolRun] = []

    def serialize_rows(rows: list[RankedDocument]) -> str:
        return json.dumps(
            [
                {
                    **_document_search_payload(row.document),
                    "score": round(row.score, 4),
                    "reason": row.reason,
                }
                for row in rows
            ],
            ensure_ascii=False,
        )

    @function_tool
    def keyword_search(query: str, max_results: int = 12) -> str:
        """Search Iris documents by lexical overlap using a standalone resolved query that preserves the user's specific subject and constraints."""
        rows = _keyword_search(_terms(query), documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool=AgentToolName.KEYWORD, query=query, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def semantic_search(query: str, max_results: int = 12) -> str:
        """Search Iris documents by semantic similarity using a standalone resolved query that preserves the user's specific subject and constraints."""
        rows = _semantic_search(query, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool=AgentToolName.SEMANTIC, query=query, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def tag_search(terms: str, max_results: int = 12) -> str:
        """Search Iris documents by comma-separated topic or tag terms."""
        normalized = {term.strip().lower() for term in terms.split(",") if term.strip()}
        rows = _tag_search(normalized, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool=AgentToolName.TAGS, query=terms, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def category_search(categories: str, max_results: int = 12) -> str:
        """Search Iris documents by comma-separated high-level categories like startups, software, culture, or personal."""
        normalized = {term.strip().lower() for term in categories.split(",") if term.strip()}
        rows = _category_search(normalized, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool=AgentToolName.CATEGORIES, query=categories, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def get_document_metadata(document_id: int) -> str:
        """Fetch metadata and a short excerpt for one Iris document by document_id."""
        document = documents_by_id.get(document_id)
        if document is None:
            tool_runs.append(AgentToolRun(tool=AgentToolName.DOCUMENT_METADATA, query=str(document_id), rows=[]))
            return json.dumps({"error": "document not found", "document_id": document_id})
        tool_runs.append(
            AgentToolRun(
                tool=AgentToolName.DOCUMENT_METADATA,
                query=str(document_id),
                rows=[RankedDocument(document=document, score=1.0, reason="document metadata lookup")],
            )
        )
        return _serialize_document_metadata(document)

    @function_tool
    def get_source_metadata(domain: str) -> str:
        """Fetch metadata about a source/blog by canonical domain."""
        normalized = domain.strip().lower()
        source = db.current_session().scalar(select(Source).where(Source.canonical_domain == normalized))
        tool_runs.append(AgentToolRun(tool=AgentToolName.SOURCE_METADATA, query=normalized, rows=[]))
        if source is None:
            return json.dumps({"error": "source not found", "domain": normalized})
        return _serialize_source_metadata(source)

    agent = Agent(
        name="Iris corpus search agent",
        model=AGENT_SEARCH_MODEL,
        output_type=AgentSearchOutput,
        instructions=AGENT_INSTRUCTIONS,
        model_settings=ModelSettings(tool_choice="auto", reasoning={"effort": AGENT_SEARCH_REASONING_EFFORT}),
        tools=[
            keyword_search,
            semantic_search,
            tag_search,
            category_search,
            get_document_metadata,
            get_source_metadata,
        ],
    )
    agent_input = _agent_input(message, conversation_context)
    with agent_search_observation(
        mode="sync",
        message=message,
        conversation_context=conversation_context,
        agent_input=agent_input,
        instructions=AGENT_INSTRUCTIONS,
        model=AGENT_SEARCH_MODEL,
        max_turns=AGENT_SEARCH_MAX_TURNS,
        session_id=session_id,
        user_id=user_id,
        trace_metadata=trace_metadata,
    ) as langfuse_observation:
        result = Runner.run_sync(agent, agent_input, max_turns=AGENT_SEARCH_MAX_TURNS)
        output = result.final_output
        if isinstance(output, AgentSearchOutput):
            answer = output.answer
            chosen_ids = output.document_ids
        else:
            answer = str(output)
            chosen_ids = []

        ranked = _rank_agent_documents(tool_runs, chosen_ids, message, limit)
        finish_agent_search_observation(
            langfuse_observation,
            answer=answer,
            chosen_ids=chosen_ids,
            ranked=ranked,
            tool_runs=tool_runs,
        )
    steps = _agent_sdk_steps(tool_runs, ranked)
    return AgentChatResult(answer=answer, results=ranked, steps=steps)


def _agent_input(message: str, conversation_context: str | None) -> str:
    if not conversation_context:
        return message
    return (
        "Use this full conversation transcript to interpret the current user message. "
        "The current message may be elliptical and may depend on earlier user constraints.\n\n"
        "Conversation transcript before the current message:\n"
        f"{conversation_context}\n\n"
        "Current user message:\n"
        f"{message}"
    )


def _serialize_document_metadata(document: Document) -> str:
    text = " ".join((document.extracted_text or "").split())
    excerpt = text[:1800] if text else None
    return json.dumps(
        {
            "document_id": document.id,
            "title": document.title,
            "url": document.url,
            "source": document.source.canonical_domain,
            "author": document.author,
            "published_at": document.published_at.isoformat() if document.published_at else None,
            "document_type": str(document.document_type.value if hasattr(document.document_type, "value") else document.document_type),
            "category": str(document.category.value if hasattr(document.category, "value") else document.category),
            "summary": document.summary,
            "one_liner": document.one_liner,
            "audience": document.audience,
            "takeaways": document.takeaways or [],
            "topics": document.topics or [],
            "excerpt": excerpt,
        },
        ensure_ascii=False,
    )


def _serialize_source_metadata(source: Source) -> str:
    profile = source.profile_analysis
    recent_documents = sorted(source.documents, key=lambda document: document.published_at or document.first_seen_at, reverse=True)[:10]
    return json.dumps(
        {
            "source_id": source.id,
            "domain": source.canonical_domain,
            "url": source.url,
            "name": source.name,
            "description": source.description,
            "status": str(source.status.value if hasattr(source.status, "value") else source.status),
            "rss_url": source.rss_url,
            "profile": None
            if profile is None
            else {
                "display_name": profile.display_name,
                "bio": profile.bio,
                "themes": profile.themes or [],
                "writing_style": profile.writing_style or [],
                "caveats": profile.caveats or [],
            },
            "recent_documents": [
                {
                    "document_id": document.id,
                    "title": document.title,
                    "url": document.url,
                    "summary": document.summary,
                    "one_liner": document.one_liner,
                    "audience": document.audience,
                    "takeaways": document.takeaways or [],
                    "topics": document.topics or [],
                }
                for document in recent_documents
            ],
        },
        ensure_ascii=False,
    )


def _rank_agent_documents(tool_runs: list[AgentToolRun], chosen_ids: list[int], query: str, limit: int) -> list[RankedDocument]:
    rows_by_id: dict[int, RankedDocument] = {}
    for run in tool_runs:
        for row in run.rows:
            existing = rows_by_id.get(row.document.id)
            reason = f"{run.tool.value}: {row.reason}"
            if existing is None or row.score > existing.score:
                rows_by_id[row.document.id] = RankedDocument(document=row.document, score=row.score, reason=reason)
            else:
                rows_by_id[row.document.id] = RankedDocument(
                    document=existing.document,
                    score=existing.score + min(0.08, row.score * 0.18),
                    reason=f"{existing.reason}; {reason}",
                )

    ranked: list[RankedDocument] = []
    seen: set[int] = set()
    for rank, document_id in enumerate(chosen_ids):
        row = rows_by_id.get(document_id)
        if not row or document_id in seen:
            continue
        ranked.append(
            RankedDocument(
                document=row.document,
                score=row.score + max(0.02, 0.12 - rank * 0.01),
                reason=f"agent selected: {row.reason}",
            )
        )
        seen.add(document_id)

    return _dedupe_ranked_documents(ranked)[:limit]


def _dedupe_ranked_documents(rows: list[RankedDocument]) -> list[RankedDocument]:
    seen_ids: set[int] = set()
    seen_identities: set[str] = set()
    deduped: list[RankedDocument] = []
    for row in rows:
        identity = _document_identity(row.document)
        if row.document.id in seen_ids or identity in seen_identities:
            continue
        seen_ids.add(row.document.id)
        seen_identities.add(identity)
        deduped.append(row)
    return deduped


def _document_identity(document: Document) -> str:
    if document.content_hash:
        return f"content:{document.content_hash}"
    if document.url:
        return f"url:{document.url.split('#', 1)[0].rstrip('/').lower()}"
    return f"id:{document.id}"


def _agent_sdk_steps(tool_runs: list[AgentToolRun], ranked: list[RankedDocument]) -> list[AgentStep]:
    steps = []
    for run in tool_runs:
        steps.append(_tool_step(run.tool, run.query, run.rows))
    return steps


def _merge_tool_outputs(tool_outputs: list[tuple[str, list[RankedDocument]]], query: str, limit: int) -> list[RankedDocument]:
    merged: dict[int, RankedDocument] = {}
    tool_weights = {
        AgentToolName.KEYWORD: 1.0,
        AgentToolName.SEMANTIC: 0.95,
        AgentToolName.TAGS: 0.35,
        AgentToolName.CATEGORIES: 0.4,
    }
    for tool_name, rows in tool_outputs:
        tool_weight = tool_weights.get(tool_name, 0.5)
        for rank, row in enumerate(rows):
            score = max(0.0, row.score) * tool_weight + max(0.0, (len(rows) - rank) / max(1, len(rows))) * 0.04 * tool_weight
            reason = f"{tool_name.value}: {row.reason}"
            existing = merged.get(row.document.id)
            if existing is None or score > existing.score:
                merged[row.document.id] = RankedDocument(document=row.document, score=score, reason=reason)
            else:
                merged[row.document.id] = RankedDocument(
                    document=existing.document,
                    score=existing.score + min(0.08, score * 0.18),
                    reason=f"{existing.reason}; {reason}",
                )

    saved_ids = search_dao.get_favorited_document_ids()
    dismissed_ids = search_dao.get_dismissed_document_ids()
    adjusted = [
        RankedDocument(
            document=row.document,
            score=row.score + (0.08 if row.document.id in saved_ids else 0.0) - (0.18 if row.document.id in dismissed_ids else 0.0),
            reason=row.reason,
        )
        for row in merged.values()
        if row.score > 0.02
    ]
    adjusted.sort(key=lambda item: item.score, reverse=True)
    candidate_pool = _rerank_candidates(query, adjusted[: max(limit * 3, 24)])
    return _dedupe_ranked_documents(_expand_with_graph_neighbors(candidate_pool[:limit], limit))[:limit]


def _keyword_search(query_terms: set[str], documents: list[Document], *, limit: int) -> list[RankedDocument]:
    rows = [
        RankedDocument(document=document, score=_keyword_score(query_terms, document), reason=f"keyword overlap {_keyword_score(query_terms, document):.0%}")
        for document in documents
    ]
    return [row for row in sorted(rows, key=lambda item: item.score, reverse=True) if row.score > 0][:limit]


def _semantic_search(query: str, documents: list[Document], *, limit: int) -> list[RankedDocument]:
    query_vector = embed_text(query)
    vector_rows = search_dao.vector_search_documents(query_vector, limit=limit)
    if vector_rows:
        return [
            RankedDocument(document=document, score=similarity, reason=f"pgvector cosine {similarity:.2f}")
            for document, similarity in vector_rows
            if similarity > 0.04
        ]
    rows: list[RankedDocument] = []
    for document in documents:
        if not document.embedding_vector:
            continue
        semantic = cosine(query_vector, loads_embedding(document.embedding_vector))
        if semantic > 0.04:
            rows.append(RankedDocument(document=document, score=semantic, reason=f"embedding cosine {semantic:.2f}"))
    rows.sort(key=lambda item: item.score, reverse=True)
    return rows[:limit]


def _tag_search(tag_terms: set[str], documents: list[Document], *, limit: int) -> list[RankedDocument]:
    if not tag_terms:
        return []
    docs_by_id = {document.id: document for document in documents}
    document_ids = list(docs_by_id)
    rows: dict[int, RankedDocument] = {}
    for document in documents:
        topics = {topic.lower() for topic in document.topics or []}
        overlap = tag_terms & topics
        if overlap:
            rows[document.id] = RankedDocument(document=document, score=0.28 + 0.12 * (len(overlap) / max(1, len(tag_terms))), reason=f"topic match: {', '.join(sorted(overlap))}")
    session = db.current_session()
    tag_rows = session.execute(
        select(DocumentTag.document_id, Tag.name, Tag.slug)
        .join(Tag, Tag.id == DocumentTag.tag_id)
        .where(DocumentTag.document_id.in_(document_ids))
    ).all()
    for document_id, name, slug in tag_rows:
        terms = {str(name).lower(), str(slug).lower()}
        overlap = tag_terms & terms
        if not overlap or document_id not in docs_by_id:
            continue
        existing = rows.get(document_id)
        score = 0.38 + 0.12 * (len(overlap) / max(1, len(tag_terms)))
        reason = f"tag match: {', '.join(sorted(overlap))}"
        rows[document_id] = RankedDocument(document=docs_by_id[document_id], score=max(score, existing.score if existing else 0.0), reason=reason)
    return sorted(rows.values(), key=lambda item: item.score, reverse=True)[:limit]


def _category_search(category_terms: set[str], documents: list[Document], *, limit: int) -> list[RankedDocument]:
    if not category_terms:
        return []
    docs_by_id = {document.id: document for document in documents}
    document_ids = list(docs_by_id)
    rows: dict[int, RankedDocument] = {}
    for document in documents:
        category = str(document.category.value if hasattr(document.category, "value") else document.category).lower()
        if category in category_terms:
            rows[document.id] = RankedDocument(document=document, score=0.42, reason=f"document category: {category}")
    session = db.current_session()
    category_rows = session.execute(
        select(DocumentCategoryAssignment.document_id, Category.slug, Category.name)
        .join(Category, Category.id == DocumentCategoryAssignment.category_id)
        .where(DocumentCategoryAssignment.document_id.in_(document_ids))
    ).all()
    for document_id, slug, name in category_rows:
        terms = {str(slug).lower(), str(name).lower()}
        overlap = category_terms & terms
        if not overlap or document_id not in docs_by_id:
            continue
        rows[document_id] = RankedDocument(document=docs_by_id[document_id], score=0.48, reason=f"category match: {', '.join(sorted(overlap))}")
    return sorted(rows.values(), key=lambda item: item.score, reverse=True)[:limit]


def _tag_query_terms(query_terms: set[str], documents: list[Document]) -> set[str]:
    known_topics = {topic.lower() for document in documents for topic in (document.topics or [])}
    return {term for term in query_terms if term in known_topics}


def _category_query_terms(query_terms: set[str]) -> set[str]:
    aliases = {
        "startup": "startups",
        "startups": "startups",
        "software": "software",
        "technology": "technology",
        "tech": "technology",
        "economics": "economics",
        "health": "health",
        "culture": "culture",
        "history": "history",
        "politics": "politics",
        "philosophy": "philosophy",
        "personal": "personal",
        "science": "science",
    }
    return {aliases[term] for term in query_terms if term in aliases}


def _tool_step(tool: AgentToolName, query: str, rows: list[RankedDocument]) -> AgentStep:
    if tool == AgentToolName.DOCUMENT_METADATA:
        title = rows[0].document.title or rows[0].document.url if rows else "Document details"
        return AgentStep(
            kind=AgentStepKind.TOOL,
            title="Inspect document",
            detail=title,
            tool=tool,
            query=query,
            hits=None,
        )
    if tool == AgentToolName.SOURCE_METADATA:
        return AgentStep(
            kind=AgentStepKind.TOOL,
            title="Inspect source",
            detail=query,
            tool=tool,
            query=query,
            hits=None,
        )
    titles = [row.document.title or row.document.url for row in rows[:3]]
    return AgentStep(
        kind=AgentStepKind.TOOL,
        title=f"Run {tool.value}",
        detail=f"Top hits: {', '.join(titles) if titles else 'none'}",
        tool=tool,
        query=query,
        hits=len(rows),
    )


def _top_unique_documents(groups: list[list[RankedDocument]], *, limit: int) -> list[Document]:
    seen: set[int] = set()
    documents: list[Document] = []
    for rows in groups:
        for row in rows:
            if row.document.id in seen:
                continue
            seen.add(row.document.id)
            documents.append(row.document)
            if len(documents) >= limit:
                return documents
    return documents


def _candidate_topic_terms(documents: list[Document], *, max_terms: int) -> set[str]:
    counts: dict[str, int] = {}
    for document in documents:
        for topic in document.topics or []:
            normalized = topic.strip().lower()
            if len(normalized) < 3:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
    return {term for term, _count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:max_terms]}


def _candidate_category_terms(documents: list[Document], *, max_terms: int) -> set[str]:
    counts: dict[str, int] = {}
    for document in documents:
        category = str(document.category.value if hasattr(document.category, "value") else document.category).lower()
        if category == "unknown":
            continue
        counts[category] = counts.get(category, 0) + 1
    return {term for term, _count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:max_terms]}


def _rerank_candidates(query: str, candidates: list[RankedDocument]) -> list[RankedDocument]:
    if not USE_LLM_RERANKER or len(candidates) <= 1:
        return candidates
    key = openai_api_key()
    if not key:
        return candidates
    try:
        order = _llm_rerank_order(key, query, candidates[:24])
    except Exception:
        return candidates
    by_id = {item.document.id: item for item in candidates}
    reranked: list[RankedDocument] = []
    seen: set[int] = set()
    for doc_id in order:
        item = by_id.get(doc_id)
        if not item or doc_id in seen:
            continue
        reranked.append(
            RankedDocument(
                document=item.document,
                score=item.score + 0.05,
                reason=f"{item.reason}, reranked for query fit",
            )
        )
        seen.add(doc_id)
    reranked.extend(item for item in candidates if item.document.id not in seen)
    return reranked


def _llm_rerank_order(api_key: str, query: str, candidates: list[RankedDocument]) -> list[int]:
    payload_candidates = [
        {
            **_document_search_payload(item.document),
            "id": item.document.id,
            "current_score": round(item.score, 4),
        }
        for item in candidates
    ]
    payload = {
        "model": SEARCH_RERANK_MODEL,
        "instructions": (
            "You rerank search results for a personal corpus of blogs and essays. Prefer documents that directly answer "
            "the query, are substantive, and are likely worth reading. Return JSON only: {\"ids\": [document ids in best order]}."
        ),
        "input": json.dumps({"query": query, "candidates": payload_candidates}, ensure_ascii=False),
        "max_output_tokens": 300,
        "store": False,
    }
    with httpx.Client(timeout=SEARCH_RERANK_TIMEOUT_SECONDS) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    data = response.json()
    text = data.get("output_text") or _response_output_text(data)
    parsed = json.loads(_extract_json_object(text))
    return [int(item) for item in parsed.get("ids", [])]


def _response_output_text(data: Mapping[str, object]) -> str:
    chunks: list[str] = []
    output = data.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if content.get("type") == "output_text" and isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text.strip(), flags=re.DOTALL)
    if not match:
        raise ValueError("reranker response did not contain JSON")
    return match.group(0)


def _expand_with_graph_neighbors(ranked: list[RankedDocument], limit: int) -> list[RankedDocument]:
    seen = {item.document.id for item in ranked}
    expanded = list(ranked)
    for item in ranked[:5]:
        links = search_dao.get_outgoing_links(item.document)
        for link in links:
            if not link.target_document_id or link.target_document_id in seen:
                continue
            target = search_dao.get_document(link.target_document_id)
            if not target or target.document_type != DocumentType.ESSAY.value:
                continue
            expanded.append(
                RankedDocument(
                    document=target,
                    score=item.score * 0.72,
                    reason=f"linked from {item.document.title or item.document.url}",
                )
            )
            seen.add(target.id)
            if len(expanded) >= limit:
                return sorted(expanded, key=lambda row: row.score, reverse=True)
    return sorted(expanded, key=lambda row: row.score, reverse=True)


def synthesize_answer(query: str, results: list[RankedDocument]) -> str:
    if not results:
        return ""
    lines = [f"For `{query}`, the strongest matches in the corpus point to:"]
    for item in results[:4]:
        title = item.document.title or item.document.url
        source = item.document.source.canonical_domain
        summary = (item.document.summary or "").strip()
        lines.append(f"- {title} ({source}): {summary[:220]}")
    return "\n".join(lines)
