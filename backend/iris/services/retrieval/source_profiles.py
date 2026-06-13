"""Generate evidence-grounded profile analyses for indexed sources."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from iris.dao import source_profiles as profile_dao
from iris.models import Document, Source, SourceProfileAnalysis
from iris.schemas.enums import DocumentType
from iris.services.common.config import SOURCE_PROFILE_MODEL, SOURCE_PROFILE_TIMEOUT_SECONDS, openai_api_key


SOCIAL_DOMAINS = (
    "twitter.com",
    "x.com",
    "github.com",
    "linkedin.com",
    "mastodon",
    "bsky.app",
    "youtube.com",
    "substack.com",
)

UNAVAILABLE_SECTIONS = ("bio", "themes", "writing_style", "strong_takes", "public_contact", "public_links")


@dataclass(frozen=True)
class ProfileInput:
    """Compressed source material for profile analysis."""

    source_id: int
    domain: str
    url: str
    fingerprint: str
    scraped_facts: dict
    documents: list[dict]


def generate_source_profile(source: Source, *, force: bool = False) -> SourceProfileAnalysis:
    """Generate and persist a profile analysis for one source."""
    documents = profile_dao.get_documents_for_profile(source.id)
    profile_input = build_profile_input(source, documents)
    existing = profile_dao.get_analysis(source.id)
    if existing and not force and existing.input_fingerprint == profile_input.fingerprint and existing.status == "succeeded":
        return existing

    key = openai_api_key()
    if not key:
        payload = fallback_profile_payload(profile_input)
        return profile_dao.upsert_analysis(
            source,
            status="missing_key",
            display_name=payload.get("display_name"),
            payload=payload,
            scraped_facts=profile_input.scraped_facts,
            unavailable_sections=payload.get("unavailable_sections", list(UNAVAILABLE_SECTIONS)),
            model=None,
            input_fingerprint=profile_input.fingerprint,
            error="missing OpenAI API key",
        )

    try:
        payload = analyze_profile_with_openai(key, profile_input)
        payload = normalize_profile_payload(payload, profile_input)
        return profile_dao.upsert_analysis(
            source,
            status="succeeded",
            display_name=payload.get("display_name"),
            payload=payload,
            scraped_facts=profile_input.scraped_facts,
            unavailable_sections=payload.get("unavailable_sections", []),
            model=SOURCE_PROFILE_MODEL,
            input_fingerprint=profile_input.fingerprint,
            error=None,
        )
    except Exception as exc:
        payload = fallback_profile_payload(profile_input)
        return profile_dao.upsert_analysis(
            source,
            status="failed",
            display_name=payload.get("display_name"),
            payload=payload,
            scraped_facts=profile_input.scraped_facts,
            unavailable_sections=payload.get("unavailable_sections", list(UNAVAILABLE_SECTIONS)),
            model=SOURCE_PROFILE_MODEL,
            input_fingerprint=profile_input.fingerprint,
            error=str(exc),
        )


def build_profile_input(source: Source, documents: list[Document]) -> ProfileInput:
    """Compress source documents into a bounded profile-analysis input bundle."""
    profile_docs = [doc for doc in documents if doc.document_type == DocumentType.PROFILE.value]
    essay_docs = [doc for doc in documents if doc.document_type == DocumentType.ESSAY.value]
    collection_docs = [doc for doc in documents if doc.document_type == DocumentType.COLLECTION.value]
    selected = select_evidence_documents(profile_docs, essay_docs, collection_docs)
    facts = scraped_facts(source, documents, profile_docs)
    doc_payloads = [document_profile_payload(doc, include_excerpt=doc in selected) for doc in selected]
    # Include metadata for every essay so the model sees the long-tail topic distribution without full text.
    selected_ids = {doc.id for doc in selected}
    for doc in essay_docs:
        if doc.id in selected_ids:
            continue
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


def select_evidence_documents(profile_docs: list[Document], essay_docs: list[Document], collection_docs: list[Document]) -> list[Document]:
    """Pick a compact, representative set of documents for full-text evidence."""
    selected: list[Document] = []
    selected.extend(profile_docs[:6])
    recent = sorted(essay_docs, key=lambda doc: (doc.published_at is not None, doc.published_at, doc.id), reverse=True)
    selected.extend(recent[:12])
    topic_seen: set[str] = set()
    for doc in essay_docs:
        topics = {topic.lower() for topic in (doc.topics or [])}
        if topics and not topics <= topic_seen:
            selected.append(doc)
            topic_seen |= topics
        if len(selected) >= 34:
            break
    longform = sorted(essay_docs, key=lambda doc: len(doc.extracted_text or ""), reverse=True)[:8]
    selected.extend(longform)
    selected.extend(collection_docs[:3])
    deduped: list[Document] = []
    seen: set[int] = set()
    for doc in selected:
        if doc.id in seen:
            continue
        seen.add(doc.id)
        deduped.append(doc)
        if len(deduped) >= 45:
            break
    return deduped


def scraped_facts(source: Source, documents: list[Document], profile_docs: list[Document]) -> dict:
    """Extract deterministic public facts from indexed source material."""
    links = public_links(source, documents)
    author_counts = Counter(doc.author.strip() for doc in documents if doc.author and doc.author.strip())
    topic_counts = Counter(topic.strip().lower() for doc in documents for topic in (doc.topics or []) if topic and topic.strip())
    return {
        "domain": source.canonical_domain,
        "homepage": source.url,
        "rss_url": source.rss_url,
        "sitemap_url": source.sitemap_url,
        "author_candidates": [name for name, _count in author_counts.most_common(5)],
        "top_topics": [{"topic": topic, "count": count} for topic, count in topic_counts.most_common(20)],
        "profile_pages": [{"id": doc.id, "title": doc.title, "url": doc.url, "summary": doc.summary} for doc in profile_docs[:8]],
        "public_links": links["links"],
        "public_contact": links["contact"],
        "document_counts": {
            "total": len(documents),
            "essay": sum(1 for doc in documents if doc.document_type == DocumentType.ESSAY.value),
            "profile": len(profile_docs),
        },
    }


def public_links(source: Source, documents: list[Document]) -> dict[str, list[dict]]:
    """Extract public links and contact hints from document text and URLs."""
    links: list[dict] = [{"label": "homepage", "url": source.url, "kind": "homepage"}]
    contact: list[dict] = []
    seen = {source.url}
    for doc in documents:
        url = doc.url
        lower = url.lower()
        if any(marker in lower for marker in ("/about", "/contact", "/bio", "/cv", "/resume")) and url not in seen:
            links.append({"label": doc.title or url, "url": url, "kind": "profile"})
            seen.add(url)
        for match in re.finditer(r"https?://[^\s)>\"]+", doc.extracted_text or ""):
            candidate = match.group(0).rstrip(".,;")
            if candidate in seen:
                continue
            host = urlparse(candidate).netloc.lower()
            if any(domain in host for domain in SOCIAL_DOMAINS):
                links.append({"label": host, "url": candidate, "kind": "social"})
                seen.add(candidate)
        if any(marker in lower for marker in ("/contact", "/about")):
            for email in re.findall(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}", doc.extracted_text or ""):
                contact.append({"label": email, "url": f"mailto:{email}", "kind": "email", "source_document_id": doc.id})
    return {"links": links[:30], "contact": contact[:10]}


def document_profile_payload(document: Document, *, include_excerpt: bool) -> dict:
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
        payload["excerpt"] = compress_text(document.extracted_text or "", max_chars=6500)
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
    return f"{head}\n\n[compressed high-signal middle]\n{middle}\n\n[ending]\n{tail}"


def analyze_profile_with_openai(api_key: str, profile_input: ProfileInput) -> dict:
    """Call the model for structured source profile analysis."""
    payload = {
        "model": SOURCE_PROFILE_MODEL,
        "instructions": (
            "Create an evidence-grounded profile analysis for an indexed personal writing source. "
            "Be playful but precise. Capture the writer's online presence, recurring interests, style, and strong takes. "
            "Do not invent identity, credentials, contact info, or claims not supported by the provided documents. "
            "If the person/name is unclear, set display_name to 'Identity unclear'. "
            "Use unavailable_sections for missing bio/themes/writing_style/strong_takes/public_contact/public_links. "
            "Strong takes should be concise claims supported by the input documents. Return JSON matching the schema."
        ),
        "input": json.dumps(
            {
                "source": {"id": profile_input.source_id, "domain": profile_input.domain, "url": profile_input.url},
                "scraped_facts": profile_input.scraped_facts,
                "documents": profile_input.documents,
            },
            ensure_ascii=False,
        ),
        "text": {"format": profile_response_format(), "verbosity": "low"},
        "reasoning": {"effort": "minimal"},
        "max_output_tokens": 3500,
        "store": False,
    }
    with httpx.Client(timeout=SOURCE_PROFILE_TIMEOUT_SECONDS) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    text = data.get("output_text") or response_output_text(data)
    if not text:
        raise ValueError("empty source profile response")
    return json.loads(text)


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
                "display_name": {"type": "string"},
                "bio": {"type": "string"},
                "themes": {"type": "array", "items": {"type": "string"}},
                "writing_style": {"type": "array", "items": {"type": "string"}},
                "strong_takes": {
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
                "public_links": {"type": "array", "items": link_schema()},
                "public_contact": {"type": "array", "items": link_schema()},
                "caveats": {"type": "array", "items": {"type": "string"}},
                "unavailable_sections": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["display_name", "bio", "themes", "writing_style", "strong_takes", "public_links", "public_contact", "caveats", "unavailable_sections"],
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
            "kind": {"type": "string"},
        },
        "required": ["label", "url", "kind"],
    }


def normalize_profile_payload(payload: dict, profile_input: ProfileInput) -> dict:
    """Normalize model output and merge deterministic public facts."""
    normalized = dict(payload)
    if not normalized.get("display_name"):
        normalized["display_name"] = "Identity unclear"
    normalized["public_links"] = profile_input.scraped_facts.get("public_links", normalized.get("public_links", []))
    normalized["public_contact"] = profile_input.scraped_facts.get("public_contact", normalized.get("public_contact", []))
    unavailable = set(normalized.get("unavailable_sections") or [])
    for section in UNAVAILABLE_SECTIONS:
        value = normalized.get(section)
        if value in (None, "", []) and section not in unavailable:
            unavailable.add(section)
    normalized["unavailable_sections"] = sorted(unavailable)
    return normalized


def fallback_profile_payload(profile_input: ProfileInput) -> dict:
    """Return a deterministic sparse profile payload when generation is unavailable."""
    facts = profile_input.scraped_facts
    themes = [item["topic"] for item in facts.get("top_topics", [])[:12]]
    unavailable = {"bio", "writing_style", "strong_takes"}
    if not facts.get("public_links"):
        unavailable.add("public_links")
    if not facts.get("public_contact"):
        unavailable.add("public_contact")
    if not themes:
        unavailable.add("themes")
    return {
        "display_name": "Identity unclear",
        "bio": "",
        "themes": themes,
        "writing_style": [],
        "strong_takes": [],
        "public_links": facts.get("public_links", []),
        "public_contact": facts.get("public_contact", []),
        "caveats": ["Generated analysis unavailable; showing scraped facts and topic aggregates only."],
        "unavailable_sections": sorted(unavailable),
    }


def response_output_text(data: dict) -> str:
    """Extract Responses API output text."""
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)
