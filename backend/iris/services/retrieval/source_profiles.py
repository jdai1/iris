"""Generate profile analyses for indexed sources."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from iris.dao import source_profiles as profile_dao
from iris.models import Document, Source, SourceProfileAnalysis
from iris.schemas.enums import DocumentType, SourceProfileAnalysisStatus, SourceProfileLinkKind
from iris.schemas.source_profiles import ProfileInput
from iris.services.common.config import SOURCE_PROFILE_MODEL, SOURCE_PROFILE_PROVIDER, SOURCE_PROFILE_TIMEOUT_SECONDS
from iris.services.llm.client import generate_json


def generate_source_profile(source: Source, *, force: bool = False) -> SourceProfileAnalysis:
    """Generate and persist a profile analysis for one source."""
    documents = profile_dao.get_documents_for_profile(source.id)
    profile_input = build_profile_input(source, documents)
    existing = profile_dao.get_analysis(source.id)
    if existing and not force and existing.input_fingerprint == profile_input.fingerprint and existing.status == SourceProfileAnalysisStatus.SUCCEEDED:
        return existing

    try:
        payload = analyze_profile(profile_input)
        payload = normalize_profile_payload(payload, profile_input)
        return profile_dao.upsert_analysis(
            source,
            status=SourceProfileAnalysisStatus.SUCCEEDED,
            display_name=payload.get("display_name"),
            bio=payload.get("bio"),
            themes=payload.get("themes"),
            writing_style=payload.get("writing_style"),
            strong_takes=payload.get("strong_takes"),
            public_links=payload.get("public_links"),
            public_contact=payload.get("public_contact"),
            caveats=payload.get("caveats"),
            scraped_facts=profile_input.scraped_facts,
            model=source_profile_model_label(),
            input_fingerprint=profile_input.fingerprint,
            error=None,
        )
    except Exception as exc:
        return profile_dao.upsert_analysis(
            source,
            status=SourceProfileAnalysisStatus.FAILED,
            display_name=None,
            bio=None,
            themes=None,
            writing_style=None,
            strong_takes=None,
            public_links=None,
            public_contact=None,
            caveats=None,
            scraped_facts=profile_input.scraped_facts,
            model=source_profile_model_label(),
            input_fingerprint=profile_input.fingerprint,
            error=str(exc),
        )


def build_profile_input(source: Source, documents: list[Document]) -> ProfileInput:
    """Compress source documents into a bounded profile-analysis input bundle."""
    profile_docs = [doc for doc in documents if doc.document_type == DocumentType.PROFILE.value]
    profile_context_docs = dedupe_documents([*profile_docs, *[doc for doc in documents if same_url(doc.url, source.url)]])
    essay_docs = [doc for doc in documents if doc.document_type == DocumentType.ESSAY.value]
    collection_docs = [doc for doc in documents if doc.document_type == DocumentType.COLLECTION.value]
    facts = scraped_facts(source, documents, profile_context_docs)
    doc_payloads = [document_profile_payload(doc, include_excerpt=True, excerpt_chars=6500) for doc in profile_context_docs]
    for doc in select_summary_documents(essay_docs, limit=50):
        doc_payloads.append(document_profile_payload(doc, include_excerpt=True, excerpt_chars=5000))
    for doc in collection_docs[:3]:
        doc_payloads.append(document_profile_payload(doc, include_excerpt=False))
    raw = json.dumps(
        {
            "source_id": source.id,
            "domain": source.canonical_domain,
            "url": source.url,
            "facts": facts,
            "documents": doc_payloads,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return ProfileInput(
        source_id=source.id,
        domain=source.canonical_domain,
        url=source.url,
        fingerprint=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        scraped_facts=facts,
        documents=doc_payloads,
    )


def select_summary_documents(essay_docs: list[Document], *, limit: int) -> list[Document]:
    """Pick a broad essay sample for summary plus capped text context."""
    recent = sorted(essay_docs, key=lambda doc: (doc.published_at is not None, doc.published_at, doc.id), reverse=True)
    selected = recent[: min(20, limit)]
    topic_seen: set[str] = set()
    for doc in essay_docs:
        if len(selected) >= limit:
            break
        topics = {topic.lower() for topic in (doc.topics or [])}
        if topics and not topics <= topic_seen:
            selected.append(doc)
            topic_seen |= topics
    deduped: list[Document] = []
    seen: set[int] = set()
    for doc in selected:
        if doc.id in seen:
            continue
        seen.add(doc.id)
        deduped.append(doc)
        if len(deduped) >= limit:
            break
    return deduped


def dedupe_documents(documents: list[Document]) -> list[Document]:
    deduped: list[Document] = []
    seen: set[int] = set()
    for doc in documents:
        if doc.id in seen:
            continue
        seen.add(doc.id)
        deduped.append(doc)
    return deduped


def scraped_facts(source: Source, documents: list[Document], profile_docs: list[Document]) -> dict:
    """Extract deterministic public facts from indexed source material."""
    links = public_links(source, profile_docs)
    author_counts = Counter(doc.author.strip() for doc in documents if doc.author and doc.author.strip())
    topic_counts = Counter(topic.strip().lower() for doc in documents for topic in (doc.topics or []) if topic and topic.strip())
    return {
        "domain": source.canonical_domain,
        "homepage": source.url,
        "rss_url": source.rss_url,
        "sitemap_url": source.sitemap_url,
        "author_candidates": [name for name, _count in author_counts.most_common(5)],
        "top_topics": [{"topic": topic, "count": count} for topic, count in topic_counts.most_common(20)],
        "profile_pages": [{"id": doc.id, "title": doc.title, "url": doc.url, "summary": doc.summary} for doc in profile_docs],
        "public_links": links["links"],
        "public_contact": links["contact"],
        "document_counts": {
            "total": len(documents),
            "essay": sum(1 for doc in documents if doc.document_type == DocumentType.ESSAY.value),
            "profile": len(profile_docs),
        },
    }


def public_links(source: Source, profile_docs: list[Document]) -> dict[str, list[dict]]:
    """Extract public link and contact hints from indexed profile pages."""
    links: list[dict] = [{"label": "homepage", "url": source.url, "kind": SourceProfileLinkKind.HOMEPAGE.value}]
    contact: list[dict] = []
    seen = {source.url}
    for doc in profile_docs:
        url = doc.url
        if url not in seen:
            links.append({"label": doc.title or url, "url": url, "kind": SourceProfileLinkKind.PROFILE.value})
            seen.add(url)
        for link in doc.outgoing_links:
            candidate = link.target_url
            if not candidate or candidate in seen:
                continue
            links.append({"label": link.anchor_text or candidate, "url": candidate, "kind": SourceProfileLinkKind.VISIBLE_LINK.value})
            seen.add(candidate)
        for match in re.finditer(r"https?://[^\s)>\"]+", doc.extracted_text or ""):
            candidate = match.group(0).rstrip(".,;")
            if candidate in seen:
                continue
            links.append({"label": candidate, "url": candidate, "kind": SourceProfileLinkKind.VISIBLE_LINK.value})
            seen.add(candidate)
        for email in re.findall(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", doc.extracted_text or ""):
            contact.append({"label": email, "url": f"mailto:{email}", "kind": SourceProfileLinkKind.EMAIL.value, "source_document_id": doc.id})
    return {"links": links[:30], "contact": contact[:10]}


def same_url(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def document_profile_payload(document: Document, *, include_excerpt: bool, excerpt_chars: int = 5000) -> dict:
    """Serialize a document for profile analysis."""
    payload = {
        "id": document.id,
        "url": document.url,
        "title": document.title,
        "author": document.author,
        "published_at": document.published_at.isoformat() if document.published_at else None,
        "document_type": document.document_type,
        "category": document.category,
        "summary": document.summary,
        "topics": document.topics or [],
    }
    if include_excerpt:
        payload["excerpt"] = compress_text(document.extracted_text or "", max_chars=excerpt_chars)
    return payload


def compress_text(text: str, *, max_chars: int) -> str:
    """Keep the beginning, high-signal middle, and ending of a long document."""
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= max_chars:
        return clean
    head = clean[: max_chars // 2]
    tail = clean[-max_chars // 4 :]
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    signal = [sentence for sentence in sentences if any(marker in sentence.lower() for marker in ("i think", "i believe", "should", "because", "the point", "lesson", "mistake", "argue"))]
    middle = " ".join(signal[:12])[: max_chars // 4]
    return f"{head}\n\n[compressed high-signal middle]\n{middle}\n\n[ending]\n{tail}"[:max_chars]


def analyze_profile(profile_input: ProfileInput) -> dict:
    """Call the configured provider for source profile analysis."""
    return generate_json(
        provider=SOURCE_PROFILE_PROVIDER,
        model=SOURCE_PROFILE_MODEL,
        instructions=profile_prompt_instructions(),
        input_payload=profile_input_payload(profile_input),
        schema=profile_response_format(),
        timeout_seconds=SOURCE_PROFILE_TIMEOUT_SECONDS,
        max_tokens=3500,
    )


def source_profile_model_label() -> str:
    return f"{SOURCE_PROFILE_PROVIDER.value}:{SOURCE_PROFILE_MODEL}"


def profile_prompt_instructions() -> str:
    return (
        "Create a profile analysis for an indexed personal writing source. "
        "Be playful but precise. Capture the writer's online presence, recurring interests, style, and strong takes. "
        "The bio should foreground concrete identity anchors supported by the input, including employers, schools, roles, locations, and major projects. "
        "Do not bury repeated school or employer evidence in themes or caveats when it is useful for identifying the person. "
        "Do not invent identity, credentials, contact info, or claims not supported by the provided documents. "
        "If the person/name is unclear, set display_name to null. "
        "Set missing fields to null instead of inventing information. "
        "Strong takes should be concise claims supported by the input documents. Return JSON matching the schema."
    )


def profile_input_payload(profile_input: ProfileInput) -> dict:
    profile_documents = [doc for doc in profile_input.documents if doc.get("document_type") == DocumentType.PROFILE.value]
    essay_documents = [doc for doc in profile_input.documents if doc.get("document_type") == DocumentType.ESSAY.value]
    collection_documents = [doc for doc in profile_input.documents if doc.get("document_type") == DocumentType.COLLECTION.value]
    return {
        "source": {"id": profile_input.source_id, "domain": profile_input.domain, "url": profile_input.url},
        "scraped_facts": profile_input.scraped_facts,
        "profile_documents": profile_documents,
        "essay_documents": essay_documents,
        "collection_documents": collection_documents,
    }


def profile_response_format() -> dict[str, object]:
    """Structured output schema for source profile analysis."""
    return {
        "type": "json_schema",
        "name": "source_profile_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "display_name": nullable_schema({"type": "string"}),
                "bio": nullable_schema({"type": "string"}),
                "themes": nullable_schema({"type": "array", "items": {"type": "string"}}),
                "writing_style": nullable_schema({"type": "array", "items": {"type": "string"}}),
                "strong_takes": {
                    "anyOf": [
                        {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "take": {"type": "string"},
                                },
                                "required": ["take"],
                            },
                        },
                        {"type": "null"},
                    ],
                },
                "public_links": nullable_schema({"type": "array", "items": link_schema()}),
                "public_contact": nullable_schema({"type": "array", "items": link_schema()}),
                "caveats": nullable_schema({"type": "array", "items": {"type": "string"}}),
            },
            "required": ["display_name", "bio", "themes", "writing_style", "strong_takes", "public_links", "public_contact", "caveats"],
        },
    }


def link_schema() -> dict[str, object]:
    """Return the structured-output schema for public profile/contact links."""
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "label": {"type": "string"},
            "url": {"type": "string"},
            "kind": enum_schema(SourceProfileLinkKind),
        },
        "required": ["label", "url", "kind"],
    }


def normalize_profile_payload(payload: dict, profile_input: ProfileInput) -> dict:
    """Normalize model output and merge deterministic public facts."""
    normalized = dict(payload)
    if profile_input.scraped_facts.get("public_links"):
        normalized["public_links"] = profile_input.scraped_facts["public_links"]
    if profile_input.scraped_facts.get("public_contact"):
        normalized["public_contact"] = profile_input.scraped_facts["public_contact"]
    return normalized


def enum_schema(enum_class: type[SourceProfileLinkKind]) -> dict[str, object]:
    return {"type": "string", "enum": sorted(enum_class.values())}


def nullable_schema(schema: dict[str, object]) -> dict[str, object]:
    return {"anyOf": [schema, {"type": "null"}]}
