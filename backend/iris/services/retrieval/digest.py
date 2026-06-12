from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from iris.services.ingestion.embedding import cosine, embed_text, loads_embedding
from iris.models import CrawlStatus, DigestItem, DigestStatus, Document, DocumentType, Feedback, FeedbackAction, Link


def _interest_vector(session: Session) -> list[float]:
    liked = session.execute(
        select(Document)
        .join(Feedback, Feedback.document_id == Document.id)
        .where(Feedback.action.in_([FeedbackAction.SAVE.value, FeedbackAction.LIKE.value, FeedbackAction.READ.value, FeedbackAction.OPEN.value]))
    ).scalars().all()
    if not liked:
        topic_rows = session.execute(select(Document.topics).where(Document.topics.is_not(None))).scalars().all()
        topics = " ".join(topic for row in topic_rows for topic in (row or []))
        return embed_text(topics or "substantive essays technology startups science writing")
    text = "\n".join(
        " ".join([doc.title or "", doc.summary or "", " ".join(doc.topics or [])])
        for doc in liked
    )
    return embed_text(text)


def populate_digest(session: Session, limit: int = 30) -> list[DigestItem]:
    existing_active = set(
        session.execute(select(DigestItem.document_id).where(DigestItem.status.in_([DigestStatus.QUEUED.value, DigestStatus.SHOWN.value]))).scalars().all()
    )
    dismissed = set(session.execute(select(Feedback.document_id).where(Feedback.action == FeedbackAction.DISMISS.value)).scalars().all())
    interest = _interest_vector(session)
    documents = session.execute(
        select(Document).where(Document.document_type == DocumentType.ESSAY.value).where(Document.crawl_status == CrawlStatus.FETCHED.value)
    ).scalars().all()
    items: list[DigestItem] = []
    for doc in documents:
        if doc.id in existing_active or doc.id in dismissed:
            continue
        linked_by_count = session.execute(select(func.count(Link.id)).where(Link.target_document_id == doc.id)).scalar_one()
        score = (
            0.68 * cosine(interest, loads_embedding(doc.embedding))
            + 0.08 * min(float(linked_by_count), 5.0)
        )
        if score <= 0.05:
            continue
        reason = "Recommended from your corpus"
        if linked_by_count:
            reason += f"; linked by {linked_by_count} indexed page{'s' if linked_by_count != 1 else ''}"
        item = DigestItem(document_id=doc.id, score=score, reason=reason, status=DigestStatus.QUEUED.value)
        session.add(item)
        items.append(item)
    items.sort(key=lambda row: row.score, reverse=True)
    for item in items[limit:]:
        session.expunge(item)
    session.flush()
    return items[:limit]


def get_digest(session: Session, limit: int = 20) -> list[DigestItem]:
    items = session.execute(
        select(DigestItem)
        .where(DigestItem.status == DigestStatus.QUEUED.value)
        .order_by(DigestItem.score.desc())
        .limit(limit)
    ).scalars().all()
    if len(items) < min(limit, 5):
        populate_digest(session, limit=limit)
        items = session.execute(
            select(DigestItem)
            .where(DigestItem.status == DigestStatus.QUEUED.value)
            .order_by(DigestItem.score.desc())
            .limit(limit)
        ).scalars().all()
    now = datetime.now(timezone.utc)
    for item in items:
        item.status = DigestStatus.SHOWN.value
        item.shown_at = now
    session.flush()
    return items


def record_feedback(
    session: Session,
    *,
    document_id: int,
    surface: str,
    action: str,
    search_id: int | None = None,
    digest_item_id: int | None = None,
) -> Feedback:
    feedback = Feedback(
        document_id=document_id,
        surface=surface,
        action=action,
        search_id=search_id,
        digest_item_id=digest_item_id,
    )
    session.add(feedback)
    if digest_item_id:
        item = session.get(DigestItem, digest_item_id)
        if item:
            item.status = {
                FeedbackAction.SAVE.value: DigestStatus.SAVED.value,
                FeedbackAction.DISMISS.value: DigestStatus.DISMISSED.value,
                FeedbackAction.SKIP.value: DigestStatus.SKIPPED.value,
            }.get(action, item.status)
    session.flush()
    return feedback
