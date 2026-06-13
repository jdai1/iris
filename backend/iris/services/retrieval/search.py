from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from pydantic import BaseModel, Field
from sqlalchemy import select

from iris.dao import db
from iris.dao import search as search_dao
from iris.services.common.config import (
    AGENT_SEARCH_MAX_TURNS,
    AGENT_SEARCH_MODEL,
    SEARCH_RERANK_MODEL,
    SEARCH_RERANK_TIMEOUT_SECONDS,
    USE_LLM_RERANKER,
    openai_api_key,
)
from iris.services.ingestion.embedding import cosine, embed_text, loads_embedding
from iris.models import Category, Document, DocumentCategoryAssignment, DocumentTag, Tag
from iris.schemas.enums import AgentStepKind, DocumentType
from iris.schemas.retrieval import RankedDocument


@dataclass(frozen=True)
class SearchToolTrace:
    tool: str
    query: str
    hits: int
    top_titles: list[str]


@dataclass(frozen=True)
class AgenticSearchResult:
    answer: str
    results: list[RankedDocument]
    tools: list[SearchToolTrace]


@dataclass(frozen=True)
class AgentStep:
    kind: AgentStepKind
    title: str
    detail: str
    tool: str | None = None
    query: str | None = None
    hits: int | None = None


@dataclass(frozen=True)
class AgentChatResult:
    answer: str
    results: list[RankedDocument]
    steps: list[AgentStep]


@dataclass(frozen=True)
class AgentToolRun:
    tool: str
    query: str
    rows: list[RankedDocument]


class AgentSearchOutput(BaseModel):
    answer: str = Field(description="A concise answer grounded in the retrieved Iris documents.")
    document_ids: list[int] = Field(
        default_factory=list,
        description="Document ids from tool results that best support the answer, in ranked order.",
    )


def _terms(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text)}


def _keyword_score(query_terms: set[str], document: Document) -> float:
    haystack = " ".join(
        item or ""
        for item in (
            document.title,
            document.author,
            document.summary,
            " ".join(document.topics or []),
            document.extracted_text[:3000] if document.extracted_text else "",
            document.source.name,
            document.source.canonical_domain,
        )
    ).lower()
    if not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in haystack)
    return hits / len(query_terms)


def search_documents(query: str, limit: int = 12, persist: bool = True) -> tuple[None, list[RankedDocument]]:
    query_vector = embed_text(query)
    query_terms = _terms(query)
    documents = search_dao.get_searchable_documents()
    saved_ids = search_dao.get_favorited_document_ids()
    dismissed_ids = search_dao.get_dismissed_document_ids()

    ranked: list[RankedDocument] = []
    for document in documents:
        semantic = cosine(query_vector, loads_embedding(document.embedding))
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
    ranked = _expand_with_graph_neighbors(candidate_pool[:limit], limit)

    return None, ranked[:limit]


def agentic_search(query: str, limit: int = 12) -> AgenticSearchResult:
    """Run explicit retrieval tools, merge their candidates, and synthesize a result."""
    documents = search_dao.get_searchable_documents()
    query_terms = _terms(query)
    tag_terms = _tag_query_terms(query_terms, documents)
    category_terms = _category_query_terms(query_terms)
    tool_outputs = [
        ("keyword", query, _keyword_search(query_terms, documents, limit=max(limit * 3, 24))),
        ("semantic", query, _semantic_search(query, documents, limit=max(limit * 3, 24))),
        ("tags", ", ".join(sorted(tag_terms)) or query, _tag_search(tag_terms, documents, limit=max(limit * 2, 16))),
        ("categories", ", ".join(sorted(category_terms)) or query, _category_search(category_terms, documents, limit=max(limit * 2, 16))),
    ]

    merged: dict[int, RankedDocument] = {}
    tool_weights = {"keyword": 1.0, "semantic": 0.95, "tags": 0.35, "categories": 0.4}
    for tool_name, _tool_query, rows in tool_outputs:
        tool_weight = tool_weights.get(tool_name, 0.5)
        for rank, row in enumerate(rows):
            score = max(0.0, row.score) * tool_weight + max(0.0, (len(rows) - rank) / max(1, len(rows))) * 0.04 * tool_weight
            reason = f"{tool_name}: {row.reason}"
            existing = merged.get(row.document.id)
            if existing is None or score > existing.score:
                merged[row.document.id] = RankedDocument(document=row.document, score=score, reason=reason)
            elif existing:
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
    ranked = _expand_with_graph_neighbors(candidate_pool[:limit], limit)[:limit]
    traces = [
        SearchToolTrace(
            tool=tool_name,
            query=tool_query,
            hits=len(rows),
            top_titles=[row.document.title or row.document.url for row in rows[:4]],
        )
        for tool_name, tool_query, rows in tool_outputs
    ]
    return AgenticSearchResult(answer=synthesize_answer(query, ranked), results=ranked, tools=traces)


def agentic_chat(message: str, limit: int = 12) -> AgentChatResult:
    """Run the OpenAI Agents SDK retrieval loop when configured, with an offline fallback."""
    if openai_api_key():
        try:
            return _openai_agentic_chat(message, limit=limit)
        except ImportError:
            pass
    return _deterministic_agentic_chat(message, limit=limit)


def _deterministic_agentic_chat(message: str, limit: int = 12) -> AgentChatResult:
    """Run a small retrieval-agent loop over the local corpus."""
    documents = search_dao.get_searchable_documents()
    query_terms = _terms(message)
    steps = [
        AgentStep(
            kind=AgentStepKind.PLAN,
            title="Plan retrieval",
            detail="Use keyword and semantic search first, inspect the candidate set, then call tag/category tools when they can sharpen recall.",
        )
    ]

    keyword_rows = _keyword_search(query_terms, documents, limit=max(limit * 3, 24))
    steps.append(_tool_step("keyword", message, keyword_rows))
    semantic_rows = _semantic_search(message, documents, limit=max(limit * 3, 24))
    steps.append(_tool_step("semantic", message, semantic_rows))

    inspected = _top_unique_documents([keyword_rows, semantic_rows], limit=10)
    topic_terms = _tag_query_terms(query_terms, documents)
    if not topic_terms:
        topic_terms = _candidate_topic_terms(inspected, max_terms=4)
    category_terms = _category_query_terms(query_terms)
    if not category_terms:
        category_terms = _candidate_category_terms(inspected, max_terms=2)
    steps.append(
        AgentStep(
            kind=AgentStepKind.OBSERVE,
            title="Inspect candidates",
            detail=(
                f"Candidate topics: {', '.join(sorted(topic_terms)) or 'none'}; "
                f"categories: {', '.join(sorted(category_terms)) or 'none'}."
            ),
        )
    )

    tag_rows = _tag_search(topic_terms, documents, limit=max(limit * 2, 16))
    steps.append(_tool_step("tags", ", ".join(sorted(topic_terms)) or message, tag_rows))
    category_rows = _category_search(category_terms, documents, limit=max(limit * 2, 16))
    steps.append(_tool_step("categories", ", ".join(sorted(category_terms)) or message, category_rows))

    ranked = _merge_tool_outputs(
        [
            ("keyword", keyword_rows),
            ("semantic", semantic_rows),
            ("tags", tag_rows),
            ("categories", category_rows),
        ],
        message,
        limit,
    )
    steps.append(
        AgentStep(
            kind=AgentStepKind.ANSWER,
            title="Merge and answer",
            detail=f"Merged {sum(len(rows) for rows in [keyword_rows, semantic_rows, tag_rows, category_rows])} tool hits into {len(ranked)} cited results.",
        )
    )
    return AgentChatResult(answer=synthesize_answer(message, ranked), results=ranked, steps=steps)


def _openai_agentic_chat(message: str, limit: int = 12) -> AgentChatResult:
    """Let the OpenAI Agents SDK choose retrieval tools and synthesize a grounded answer."""
    from agents import Agent, Runner, function_tool

    key = openai_api_key()
    if key:
        os.environ.setdefault("OPENAI_API_KEY", key)

    documents = search_dao.get_searchable_documents()
    tool_runs: list[AgentToolRun] = []

    def serialize_rows(rows: list[RankedDocument]) -> str:
        return json.dumps(
            [
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
            ],
            ensure_ascii=False,
        )

    @function_tool
    def keyword_search(query: str, max_results: int = 12) -> str:
        """Search Iris documents by lexical overlap in title, summary, topics, text, and source metadata."""
        rows = _keyword_search(_terms(query), documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool="keyword", query=query, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def semantic_search(query: str, max_results: int = 12) -> str:
        """Search Iris documents by semantic similarity against stored embeddings."""
        rows = _semantic_search(query, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool="semantic", query=query, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def tag_search(terms: str, max_results: int = 12) -> str:
        """Search Iris documents by comma-separated topic or tag terms."""
        normalized = {term.strip().lower() for term in terms.split(",") if term.strip()}
        rows = _tag_search(normalized, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool="tags", query=terms, rows=rows))
        return serialize_rows(rows)

    @function_tool
    def category_search(categories: str, max_results: int = 12) -> str:
        """Search Iris documents by comma-separated high-level categories like startups, software, culture, or personal."""
        normalized = {term.strip().lower() for term in categories.split(",") if term.strip()}
        rows = _category_search(normalized, documents, limit=max(1, min(max_results, 30)))
        tool_runs.append(AgentToolRun(tool="categories", query=categories, rows=rows))
        return serialize_rows(rows)

    agent = Agent(
        name="Iris corpus search agent",
        model=AGENT_SEARCH_MODEL,
        output_type=AgentSearchOutput,
        instructions=(
            "You answer questions over a personal corpus of indexed blogs and essays. "
            "You have four retrieval tools: keyword_search, semantic_search, tag_search, and category_search. "
            "Choose tools based on the user's question. Use more than one tool when it improves recall or disambiguation. "
            "Only cite documents returned by tools. Return document_ids for the best supporting documents. "
            "If the corpus has weak matches, say that directly and still return the nearest useful documents."
        ),
        tools=[keyword_search, semantic_search, tag_search, category_search],
    )
    result = Runner.run_sync(agent, message, max_turns=AGENT_SEARCH_MAX_TURNS)
    output = result.final_output
    if isinstance(output, AgentSearchOutput):
        answer = output.answer
        chosen_ids = output.document_ids
    else:
        answer = str(output)
        chosen_ids = []

    ranked = _rank_agent_documents(tool_runs, chosen_ids, message, limit)
    if not ranked and tool_runs:
        ranked = _merge_tool_outputs([(run.tool, run.rows) for run in tool_runs], message, limit)
    steps = _agent_sdk_steps(tool_runs, ranked)
    steps.append(
        AgentStep(
            kind=AgentStepKind.ANSWER,
            title="Agent final answer",
            detail=f"OpenAI Agents SDK completed with {len(tool_runs)} tool call(s) and {len(ranked)} persisted citation(s).",
        )
    )
    return AgentChatResult(answer=answer or synthesize_answer(message, ranked), results=ranked, steps=steps)


def _rank_agent_documents(tool_runs: list[AgentToolRun], chosen_ids: list[int], query: str, limit: int) -> list[RankedDocument]:
    rows_by_id: dict[int, RankedDocument] = {}
    for run in tool_runs:
        for row in run.rows:
            existing = rows_by_id.get(row.document.id)
            reason = f"{run.tool}: {row.reason}"
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

    if len(ranked) < limit:
        fallback = _merge_tool_outputs([(run.tool, run.rows) for run in tool_runs], query, limit)
        ranked.extend(row for row in fallback if row.document.id not in seen)
    return ranked[:limit]


def _agent_sdk_steps(tool_runs: list[AgentToolRun], ranked: list[RankedDocument]) -> list[AgentStep]:
    steps = [
        AgentStep(
            kind=AgentStepKind.PLAN,
            title="Run OpenAI agent loop",
            detail=(
                "The model controlled the loop through the OpenAI Agents SDK, choosing retrieval tools and receiving "
                "their outputs before producing a final structured answer."
            ),
        )
    ]
    for run in tool_runs:
        steps.append(_tool_step(run.tool, run.query, run.rows))
    steps.append(
        AgentStep(
            kind=AgentStepKind.OBSERVE,
            title="Persist selected citations",
            detail=f"Stored the top {len(ranked)} document citation(s) from the agent's chosen tool results.",
        )
    )
    return steps


def _merge_tool_outputs(tool_outputs: list[tuple[str, list[RankedDocument]]], query: str, limit: int) -> list[RankedDocument]:
    merged: dict[int, RankedDocument] = {}
    tool_weights = {"keyword": 1.0, "semantic": 0.95, "tags": 0.35, "categories": 0.4}
    for tool_name, rows in tool_outputs:
        tool_weight = tool_weights.get(tool_name, 0.5)
        for rank, row in enumerate(rows):
            score = max(0.0, row.score) * tool_weight + max(0.0, (len(rows) - rank) / max(1, len(rows))) * 0.04 * tool_weight
            reason = f"{tool_name}: {row.reason}"
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
    return _expand_with_graph_neighbors(candidate_pool[:limit], limit)[:limit]


def _keyword_search(query_terms: set[str], documents: list[Document], *, limit: int) -> list[RankedDocument]:
    rows = [
        RankedDocument(document=document, score=_keyword_score(query_terms, document), reason=f"keyword overlap {_keyword_score(query_terms, document):.0%}")
        for document in documents
    ]
    return [row for row in sorted(rows, key=lambda item: item.score, reverse=True) if row.score > 0][:limit]


def _semantic_search(query: str, documents: list[Document], *, limit: int) -> list[RankedDocument]:
    query_vector = embed_text(query)
    rows: list[RankedDocument] = []
    for document in documents:
        if not document.embedding:
            continue
        semantic = cosine(query_vector, loads_embedding(document.embedding))
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


def _tool_step(tool: str, query: str, rows: list[RankedDocument]) -> AgentStep:
    titles = [row.document.title or row.document.url for row in rows[:3]]
    return AgentStep(
        kind=AgentStepKind.TOOL,
        title=f"Run {tool}",
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
            "id": item.document.id,
            "title": item.document.title,
            "source": item.document.source.canonical_domain,
            "summary": item.document.summary,
            "topics": item.document.topics or [],
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
        return "No strong matches found in the indexed corpus yet."
    lines = [f"For `{query}`, the strongest matches in the corpus point to:"]
    for item in results[:4]:
        title = item.document.title or item.document.url
        source = item.document.source.canonical_domain
        summary = (item.document.summary or "").strip()
        lines.append(f"- {title} ({source}): {summary[:220]}")
    return "\n".join(lines)
