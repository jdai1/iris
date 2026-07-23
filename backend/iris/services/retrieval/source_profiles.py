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


SOURCE_PROFILE_AUDIENCES = [
    "Software engineers",
    "Engineering leaders",
    "Founders and operators",
    "AI/ML practitioners",
    "AI policy and safety readers",
    "Mathematics readers",
    "Academics and researchers",
    "Rationalist and EA readers",
    "Policy and economics readers",
    "Writers and bloggers",
    "Productivity and learning readers",
    "General curious readers",
]

SOURCE_PROFILE_THEMES = [
    "Software engineering",
    "Engineering leadership",
    "Startups and company building",
    "AI and machine learning",
    "AI policy and safety",
    "Mathematics",
    "Statistics and probability",
    "Economics",
    "Effective altruism",
    "Rationality",
    "Philosophy",
    "Social theory",
    "Politics and policy",
    "Culture and media",
    "Writing and communication",
    "Productivity and learning",
    "Personal essays",
    "Career",
    "Science and research",
    "Internet and platforms",
    "Games and puzzles",
]

SOURCE_PROFILE_STYLES = [
    "Technical",
    "Analytical",
    "Practical",
    "Narrative",
    "Personal",
    "Opinionated",
    "Exploratory",
    "Research-heavy",
    "Conversational",
    "Dense",
    "Clear",
    "Playful",
    "Polemic",
    "Reflective",
]


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
            audiences=payload.get("audiences"),
            themes=payload.get("themes"),
            writing_style=payload.get("writing_style"),
            strong_takes=payload.get("opinions") or payload.get("strong_takes"),
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
            audiences=None,
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
        "one_liner": document.one_liner,
        "audience": document.audience,
        "takeaways": document.takeaways or [],
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
        "Write for a reader deciding whether to click into this source, follow the writer, or use the source in search results. "
        "Optimize for useful orientation: what this source is good for, what questions or problems it keeps returning to, "
        "what kind of reader would benefit, and what makes the writing distinctive. "
        "Do not waste space on generic website facts like having a homepage, a GitHub link, a blog title, or no known contact info unless that fact materially helps the reader. "
        "Prefer durable patterns across multiple documents over one-off curiosities, jokes, tags, or clever phrasing. "
        "The bio should be 2-4 plainspoken sentences with concrete identity anchors only when strongly supported, "
        "including employers, schools, roles, locations, and major projects when they matter for reader orientation. "
        "Do not make the bio a list of disconnected topics; explain the throughline. "
        "Audiences must be selected from the provided audience list; choose at most 4 primary reader groups. "
        "Themes must be selected from the provided writes-about list; choose 3-6 broad labels that explain the source without sprawling. "
        "Writing style must be selected from the provided style list; choose 2-4 compact labels. "
        "Opinions should be recurring author beliefs or foundational claims that appear across the source, not one-off article takeaways. "
        "Phrase each opinion as a concise belief the author seems to hold, ideally useful for predicting what they will argue elsewhere. "
        "Each opinion should be one short sentence, ideally under 18 words and never more than 24 words. "
        "Avoid generic intellectual virtues like precision, clarity, nuance, curiosity, or rigor unless the claim says something specific about a domain, tradeoff, or consequence. "
        "Caveats should only mention uncertainty that prevents a misleading profile; omit caveats about missing employer, school, location, or contact info unless the missing information directly affects the profile. "
        "Do not invent identity, credentials, contact info, or claims not supported by the provided documents. "
        "If the person/name is unclear, set display_name to null. "
        "Set missing fields to null instead of inventing information. "
        "Return JSON matching the schema."
    )


def profile_input_payload(profile_input: ProfileInput) -> dict:
    profile_documents = [doc for doc in profile_input.documents if doc.get("document_type") == DocumentType.PROFILE.value]
    essay_documents = [doc for doc in profile_input.documents if doc.get("document_type") == DocumentType.ESSAY.value]
    collection_documents = [doc for doc in profile_input.documents if doc.get("document_type") == DocumentType.COLLECTION.value]
    return {
        "source": {"id": profile_input.source_id, "domain": profile_input.domain, "url": profile_input.url},
        "allowed_audiences": SOURCE_PROFILE_AUDIENCES,
        "allowed_writes_about": SOURCE_PROFILE_THEMES,
        "allowed_styles": SOURCE_PROFILE_STYLES,
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
                "audiences": nullable_schema({"type": "array", "items": {"type": "string", "enum": SOURCE_PROFILE_AUDIENCES}, "maxItems": 4}),
                "themes": nullable_schema({"type": "array", "items": {"type": "string", "enum": SOURCE_PROFILE_THEMES}, "minItems": 3, "maxItems": 6}),
                "writing_style": nullable_schema({"type": "array", "items": {"type": "string", "enum": SOURCE_PROFILE_STYLES}, "minItems": 2, "maxItems": 4}),
                "opinions": {
                    "anyOf": [
                        {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "opinion": {"type": "string", "maxLength": 180},
                                },
                                "required": ["opinion"],
                            },
                        },
                        {"type": "null"},
                    ],
                },
                "public_links": nullable_schema({"type": "array", "items": link_schema()}),
                "public_contact": nullable_schema({"type": "array", "items": link_schema()}),
                "caveats": nullable_schema({"type": "array", "items": {"type": "string"}}),
            },
            "required": ["display_name", "bio", "audiences", "themes", "writing_style", "opinions", "public_links", "public_contact", "caveats"],
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
    normalized["audiences"] = _normalize_controlled_list(normalized.get("audiences"), SOURCE_PROFILE_AUDIENCES, limit=4)
    normalized["themes"] = _normalize_controlled_list(normalized.get("themes"), SOURCE_PROFILE_THEMES, limit=6)
    normalized["writing_style"] = _normalize_controlled_list(normalized.get("writing_style"), SOURCE_PROFILE_STYLES, limit=4)
    normalized["opinions"] = _normalize_opinions(normalized.get("opinions") or normalized.get("strong_takes"))
    if profile_input.scraped_facts.get("public_links"):
        normalized["public_links"] = profile_input.scraped_facts["public_links"]
    if profile_input.scraped_facts.get("public_contact"):
        normalized["public_contact"] = profile_input.scraped_facts["public_contact"]
    return normalized


def _normalize_opinions(value: object) -> list[dict] | None:
    if not isinstance(value, list):
        return None
    opinions: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            text = item.get("opinion") or item.get("take")
        else:
            text = item
        opinion = str(text or "").strip()
        if not opinion:
            continue
        opinions.append({"take": opinion[:180]})
        if len(opinions) >= 4:
            break
    return opinions or None


def _normalize_controlled_list(value: object, allowed: list[str], *, limit: int) -> list[str] | None:
    if not isinstance(value, list):
        return None
    allowed_set = set(allowed)
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in allowed_set or item in normalized:
            continue
        normalized.append(item)
        if len(normalized) >= limit:
            break
    return normalized or None


def enum_schema(enum_class: type[SourceProfileLinkKind]) -> dict[str, object]:
    return {"type": "string", "enum": sorted(enum_class.values())}


def nullable_schema(schema: dict[str, object]) -> dict[str, object]:
    return {"anyOf": [schema, {"type": "null"}]}
