from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from iris.models import DocumentType
from iris.services.common.config import (
    DOCUMENT_CLASSIFIER_MODEL,
    DOCUMENT_CLASSIFIER_TIMEOUT_SECONDS,
    MissingOpenAIKeyError,
    require_openai_api_key,
)
from iris.services.common.language import looks_non_english


logger = logging.getLogger("iris.document_classifier")


@dataclass(frozen=True)
class DocumentClassification:
    document_type: str
    confidence: float
    reason: str


COLLECTION_PATH_MARKERS = (
    "/archive",
    "/archives",
    "/blog",
    "/category/",
    "/categories/",
    "/feed",
    "/links",
    "/reading",
    "/resources",
    "/tag/",
    "/tags/",
    "/topics/",
)

PROFILE_PATH_MARKERS = (
    "/about",
    "/bio",
    "/contact",
    "/cv",
    "/now",
    "/portfolio",
    "/projects",
    "/resume",
)

REFERENCE_PATH_MARKERS = (
    "/api/",
    "/docs/",
    "/documentation",
    "/manual",
    "/privacy",
    "/reference",
)

COLLECTION_TITLE_MARKERS = (
    "archive",
    "archives",
    "blog",
    "blogroll",
    "bookshelf",
    "category",
    "links",
    "posts",
    "reading",
    "resources",
    "tag",
    "tags",
)

PROFILE_TITLE_MARKERS = (
    "about",
    "bio",
    "contact",
    "cv",
    "portfolio",
    "projects",
    "resume",
)

REFERENCE_TITLE_MARKERS = (
    "api",
    "documentation",
    "manual",
    "privacy policy",
    "reference",
    "terms",
)

SPAM_GAMBLING_MARKERS = (
    "betting",
    "casino",
    "gambling",
    "sportsbook",
    "토토",
    "먹튀",
    "카지노",
)


def classify_document(
    *,
    url: str,
    title: str | None,
    text: str,
    link_count: int,
    has_author: bool = False,
    has_published_date: bool = False,
) -> DocumentClassification:
    words = re.findall(r"\w+", text)
    word_count = len(words)
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", text))
    paragraph_count = len([part for part in re.split(r"\n{2,}", text.strip()) if len(part.split()) >= 8])
    title_lower = (title or "").lower()
    combined_text = f"{title or ''}\n{text}"
    path = urlparse(url).path.lower()
    link_density = link_count / max(word_count / 100.0, 1.0)

    if looks_non_english(combined_text):
        return DocumentClassification(DocumentType.IGNORE.value, 0.95, "primarily non-English text")

    if _looks_like_gambling_spam(combined_text):
        return DocumentClassification(DocumentType.IGNORE.value, 0.95, "casino/betting spam content")

    if _path_has_marker(path, REFERENCE_PATH_MARKERS) or _title_has_marker(title_lower, REFERENCE_TITLE_MARKERS):
        return DocumentClassification(DocumentType.REFERENCE.value, 0.85, "reference/docs/legal marker")

    if _path_has_marker(path, PROFILE_PATH_MARKERS) or (
        _title_has_marker(title_lower, PROFILE_TITLE_MARKERS) and word_count < 1200
    ):
        return DocumentClassification(DocumentType.PROFILE.value, 0.75, "profile/about marker")

    if _path_has_marker(path, COLLECTION_PATH_MARKERS) or _title_has_marker(title_lower, COLLECTION_TITLE_MARKERS):
        if link_count >= 5 or link_density >= 1.2 or word_count < 900:
            return DocumentClassification(DocumentType.COLLECTION.value, 0.85, "collection path/title marker")

    if link_count >= 20 and word_count < 180:
        return DocumentClassification(DocumentType.COLLECTION.value, 0.85, "many links with limited prose")

    if link_density >= 4.0 and paragraph_count <= 2 and word_count < 300:
        return DocumentClassification(DocumentType.COLLECTION.value, 0.75, "high link density")

    if word_count < 80:
        return DocumentClassification(DocumentType.IGNORE.value, 0.95, f"too short: {word_count} words")

    if sentence_count < 6 and word_count < 500:
        return DocumentClassification(DocumentType.IGNORE.value, 0.7, "not enough sentence-level prose")

    confidence = 0.65
    if word_count >= 700 and sentence_count >= 10:
        confidence = 0.85
    heuristic = DocumentClassification(
        DocumentType.ESSAY.value,
        confidence,
        f"substantive prose: {word_count} words",
    )
    if _should_review_with_llm(
        word_count=word_count,
        sentence_count=sentence_count,
        paragraph_count=paragraph_count,
        link_density=link_density,
        confidence=confidence,
    ):
        try:
            llm_classification = _classify_document_with_llm(
                url=url,
                title=title,
                text=text,
                word_count=word_count,
                sentence_count=sentence_count,
                paragraph_count=paragraph_count,
                link_count=link_count,
                link_density=link_density,
                heuristic=heuristic,
            )
        except MissingOpenAIKeyError:
            raise
        except Exception as exc:
            logger.warning("Document classifier failed for %s: %s", url, exc)
            llm_classification = None
        if llm_classification:
            return llm_classification
    return heuristic


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _path_has_marker(path: str, markers: tuple[str, ...]) -> bool:
    clean = path.rstrip("/") or "/"
    for marker in markers:
        marker_clean = marker.rstrip("/")
        if marker.endswith("/"):
            if marker in path:
                return True
        elif clean == marker_clean or clean.startswith(f"{marker_clean}/"):
            return True
    return False


def _title_has_marker(title: str, markers: tuple[str, ...]) -> bool:
    clean = re.sub(r"[^a-z0-9]+", " ", title).strip()
    for marker in markers:
        normalized = marker.strip("/").replace("/", " ").strip()
        if clean == normalized or clean.startswith(f"{normalized} "):
            return True
    return False


def _looks_like_gambling_spam(text: str) -> bool:
    text_lower = text.lower()
    marker_hits = sum(1 for marker in SPAM_GAMBLING_MARKERS if marker in text_lower)
    if marker_hits >= 2:
        return True
    spam_repetition = len(re.findall(r"(먹튀|카지노|토토)", text))
    return spam_repetition >= 3


def _should_review_with_llm(
    *,
    word_count: int,
    sentence_count: int,
    paragraph_count: int,
    link_density: float,
    confidence: float,
) -> bool:
    if word_count >= 1100 and sentence_count >= 12 and paragraph_count >= 3 and link_density < 1.5:
        return False
    if confidence < 0.8:
        return True
    if word_count < 900:
        return True
    if link_density >= 1.0:
        return True
    return False


def _classify_document_with_llm(
    *,
    url: str,
    title: str | None,
    text: str,
    word_count: int,
    sentence_count: int,
    paragraph_count: int,
    link_count: int,
    link_density: float,
    heuristic: DocumentClassification,
) -> DocumentClassification | None:
    key = require_openai_api_key(f"document classification ({url})")
    excerpt = re.sub(r"\s+", " ", text).strip()[:6000]
    payload = {
        "model": DOCUMENT_CLASSIFIER_MODEL,
        "instructions": (
            "Classify a crawled web page for Iris, a corpus of substantive written thought. "
            "Use document_type values only from: essay, collection, profile, reference, ignore. "
            "essay means a standalone substantive written piece, including personal opinions, book reports, "
            "media reviews, or analytical posts. collection means an index/archive/link list/anthology page. "
            "profile means about/contact/CV/homepage biography. reference means docs/legal/reference material. "
            "ignore means too thin, spam, non-English, or not useful written content. "
            "Return JSON only with keys: document_type string, confidence number 0-1, reason string."
        ),
        "input": json.dumps(
            {
                "url": url,
                "title": title,
                "word_count": word_count,
                "sentence_count": sentence_count,
                "paragraph_count": paragraph_count,
                "link_count": link_count,
                "link_density": round(link_density, 3),
                "heuristic": {
                    "document_type": heuristic.document_type,
                    "confidence": heuristic.confidence,
                    "reason": heuristic.reason,
                },
                "excerpt": excerpt,
            },
            ensure_ascii=False,
        ),
        "max_output_tokens": 240,
        "store": False,
    }
    with httpx.Client(timeout=DOCUMENT_CLASSIFIER_TIMEOUT_SECONDS) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    data = response.json()
    text_out = data.get("output_text") or _response_output_text(data)
    parsed = json.loads(_extract_json_object(text_out))
    document_type = _normalize_document_type(parsed.get("document_type"))
    try:
        confidence = max(0.0, min(float(parsed.get("confidence")), 1.0))
    except (TypeError, ValueError):
        confidence = heuristic.confidence
    reason = str(parsed.get("reason") or "LLM document classification").strip()[:1000]
    return DocumentClassification(document_type, confidence, reason)


def _normalize_document_type(value: object) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
    if normalized in DocumentType.values():
        return normalized
    if any(term in normalized for term in ("archive", "index", "links", "anthology", "collection")):
        return DocumentType.COLLECTION.value
    if any(term in normalized for term in ("about", "bio", "profile", "contact", "cv", "resume")):
        return DocumentType.PROFILE.value
    if any(term in normalized for term in ("docs", "documentation", "reference", "legal")):
        return DocumentType.REFERENCE.value
    if any(term in normalized for term in ("ignore", "thin", "spam")):
        return DocumentType.IGNORE.value
    return DocumentType.ESSAY.value


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
        raise ValueError("document classifier response did not contain JSON")
    return match.group(0)
