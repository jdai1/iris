from __future__ import annotations

from iris.dao import digest as digest_dao
from iris.services.ingestion.embedding import cosine, embed_text, loads_embedding
from iris.schemas.retrieval import DigestRecommendation


def _interest_vector() -> list[float]:
    liked = digest_dao.get_liked_documents_for_interest()
    if not liked:
        topic_rows = digest_dao.get_all_document_topics()
        topics = " ".join(topic for row in topic_rows for topic in (row or []))
        return embed_text(topics or "substantive essays technology startups science writing")
    text = "\n".join(
        " ".join([doc.title or "", doc.summary or "", " ".join(doc.topics or [])])
        for doc in liked
    )
    return embed_text(text)


def compute_digest(limit: int = 30) -> list[DigestRecommendation]:
    excluded = digest_dao.get_dismissed_or_read_document_ids()
    interest = _interest_vector()
    documents = digest_dao.get_digest_candidate_documents()
    candidates: list[DigestRecommendation] = []
    for doc in documents:
        if doc.id in excluded:
            continue
        linked_by_count = digest_dao.count_inbound_links(doc)
        score = (
            0.68 * cosine(interest, loads_embedding(doc.embedding))
            + 0.08 * min(float(linked_by_count), 5.0)
        )
        if score <= 0.05:
            continue
        reason = "Recommended from your corpus"
        if linked_by_count:
            reason += f"; linked by {linked_by_count} indexed page{'s' if linked_by_count != 1 else ''}"
        candidates.append(DigestRecommendation(document=doc, score=score, reason=reason))
    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:limit]


def get_digest(limit: int = 20) -> list[DigestRecommendation]:
    return compute_digest(limit=limit)
