from __future__ import annotations

import re
import json
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from iris.config import SEARCH_RERANK_MODEL, SEARCH_RERANK_TIMEOUT_SECONDS, USE_LLM_RERANKER, openai_api_key
from iris.embedding import cosine, embed_text, loads_embedding
from iris.models import Document, Feedback, Link, Search, SearchResult


@dataclass(frozen=True)
class RankedDocument:
    document: Document
    score: float
    reason: str


def _terms(text: str) -> set[str]:
    return {word.lower() for word in re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text)}


def _keyword_score(query_terms: set[str], document: Document) -> float:
    haystack = " ".join(
        item or ""
        for item in (
            document.title,
            document.author,
            document.summary,
            document.topics,
            document.extracted_text[:3000] if document.extracted_text else "",
            document.source.name,
            document.source.canonical_domain,
        )
    ).lower()
    if not query_terms:
        return 0.0
    hits = sum(1 for term in query_terms if term in haystack)
    return hits / len(query_terms)


def search_documents(session: Session, query: str, limit: int = 12, persist: bool = True) -> tuple[Search | None, list[RankedDocument]]:
    query_vector = embed_text(query)
    query_terms = _terms(query)
    documents = session.execute(
        select(Document)
        .join(Document.source)
        .where(Document.document_type == "essay")
        .where(Document.crawl_status == "fetched")
    ).scalars().all()

    saved_ids = set(
        session.execute(select(Feedback.document_id).where(Feedback.action.in_(["save", "like", "read"]))).scalars().all()
    )
    dismissed_ids = set(
        session.execute(select(Feedback.document_id).where(Feedback.action == "dismiss")).scalars().all()
    )

    ranked: list[RankedDocument] = []
    for document in documents:
        semantic = cosine(query_vector, loads_embedding(document.embedding))
        keyword = _keyword_score(query_terms, document)
        quality = document.quality_score or 0.0
        feedback_bonus = 0.08 if document.id in saved_ids else 0.0
        feedback_penalty = 0.18 if document.id in dismissed_ids else 0.0
        score = (0.45 * semantic) + (0.4 * keyword) + (0.15 * quality) + feedback_bonus - feedback_penalty
        if score <= 0.03:
            continue
        reason_bits = []
        if keyword > 0:
            reason_bits.append(f"keyword overlap {keyword:.0%}")
        if semantic > 0.12:
            reason_bits.append("semantic match")
        if quality > 0.7:
            reason_bits.append("high-quality longform")
        if not reason_bits:
            reason_bits.append("related corpus item")
        ranked.append(RankedDocument(document=document, score=score, reason=", ".join(reason_bits)))

    ranked.sort(key=lambda item: item.score, reverse=True)
    candidate_pool = ranked[: max(limit * 3, 24)]
    candidate_pool = _rerank_candidates(query, candidate_pool)
    ranked = _expand_with_graph_neighbors(session, candidate_pool[:limit], limit)

    search_row: Search | None = None
    if persist:
        answer = synthesize_answer(query, ranked[:6])
        search_row = Search(query=query, answer=answer)
        session.add(search_row)
        session.flush()
        for idx, item in enumerate(ranked[:limit], start=1):
            session.add(
                SearchResult(
                    search_id=search_row.id,
                    document_id=item.document.id,
                    rank=idx,
                    score=item.score,
                    reason=item.reason,
                )
            )
        session.flush()
    return search_row, ranked[:limit]


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
            "topics": item.document.topics,
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


def _response_output_text(data: dict) -> str:
    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks)


def _extract_json_object(text: str) -> str:
    match = re.search(r"\{.*\}", text.strip(), flags=re.DOTALL)
    if not match:
        raise ValueError("reranker response did not contain JSON")
    return match.group(0)


def _expand_with_graph_neighbors(session: Session, ranked: list[RankedDocument], limit: int) -> list[RankedDocument]:
    seen = {item.document.id for item in ranked}
    expanded = list(ranked)
    for item in ranked[:5]:
        links = session.execute(select(Link).where(Link.source_document_id == item.document.id)).scalars().all()
        for link in links:
            if not link.target_document_id or link.target_document_id in seen:
                continue
            target = session.get(Document, link.target_document_id)
            if not target or target.document_type != "essay":
                continue
            expanded.append(
                RankedDocument(
                    document=target,
                    score=item.score * 0.72,
                    reason=f"linked from {item.document.title or item.document.final_url}",
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
        title = item.document.title or item.document.final_url
        source = item.document.source.canonical_domain
        summary = (item.document.summary or "").strip()
        lines.append(f"- {title} ({source}): {summary[:220]}")
    return "\n".join(lines)
