from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from urllib.parse import urlparse

import httpx

from iris.schemas.enums import DocumentType
from iris.schemas.ingestion import DocumentAnalysis, DocumentClassification
from iris.services.common.config import (
    DOCUMENT_CLASSIFIER_MODEL,
    DOCUMENT_CLASSIFIER_TIMEOUT_SECONDS,
    MissingOpenAIKeyError,
    require_openai_api_key,
)
from iris.services.common.language import looks_non_english


logger = logging.getLogger("iris.document_classifier")


COLLECTION_EXACT_PATH_MARKERS = (
    "/archive",
    "/archives",
    "/blog",
    "/feed",
    "/links",
    "/reading",
    "/resources",
)

COLLECTION_PREFIX_PATH_MARKERS = (
    "/category/",
    "/categories/",
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

DOCUMENT_CATEGORY_SLUGS = (
    "ai",
    "software",
    "work",
    "productivity",
    "rationality",
    "philosophy",
    "money",
    "philanthropy",
    "health",
    "dating",
    "culture",
    "politics",
    "history",
    "science",
    "personal",
    "writing",
    "fiction",
    "education",
)


def _document_analysis_response_format() -> dict[str, object]:
    """Return the structured-output schema for document metadata analysis."""
    return {
        "type": "json_schema",
        "name": "document_analysis",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "title": {"type": ["string", "null"]},
                "summary": {"type": "string"},
                "topics": {"type": "array", "items": {"type": "string"}},
                "category_slug": {"type": ["string", "null"], "enum": [*DOCUMENT_CATEGORY_SLUGS, None]},
                "document_type": {
                    "type": "string",
                    "enum": [
                        DocumentType.ESSAY.value,
                        DocumentType.COLLECTION.value,
                        DocumentType.PROFILE.value,
                        DocumentType.REFERENCE.value,
                        DocumentType.IGNORE.value,
                    ],
                },
            },
            "required": ["title", "summary", "topics", "category_slug", "document_type"],
        },
    }


def classify_document(
    *,
    url: str,
    title: str | None,
    text: str,
    link_count: int,
    has_author: bool = False,
    has_published_date: bool = False,
) -> DocumentClassification:
    """Return only the document type classification from full LLM analysis."""
    analysis = analyze_document(
        url=url,
        metadata_title=title,
        text=text,
        link_count=link_count,
        has_author=has_author,
        has_published_date=has_published_date,
    )
    return DocumentClassification(analysis.document_type, "LLM document analysis")


def analyze_document(
    *,
    url: str,
    metadata_title: str | None,
    text: str,
    link_count: int,
    has_author: bool = False,
    has_published_date: bool = False,
) -> DocumentAnalysis:
    """Analyze extracted document text into typed metadata and document type."""
    words = re.findall(r"\w+", text)
    word_count = len(words)
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", text))
    paragraph_count = len([part for part in re.split(r"\n{2,}", text.strip()) if len(part.split()) >= 8])
    title_lower = (metadata_title or "").lower()
    combined_text = f"{metadata_title or ''}\n{text}"
    path = urlparse(url).path.lower()
    path_label = _path_label(path)
    link_density = link_count / max(word_count / 100.0, 1.0)

    if looks_non_english(combined_text):
        return _fallback_analysis(metadata_title, text, DocumentType.IGNORE.value)

    if _looks_like_gambling_spam(combined_text):
        return _fallback_analysis(metadata_title, text, DocumentType.IGNORE.value)

    heuristic = _heuristic_document_guess(
        path=path,
        title_lower=title_lower,
        word_count=word_count,
        sentence_count=sentence_count,
        paragraph_count=paragraph_count,
        link_count=link_count,
        link_density=link_density,
    )
    hints = _page_hints(path=path, title_lower=title_lower, word_count=word_count)
    return _analyze_document_with_llm(
        url=url,
        metadata_title=metadata_title,
        text=text,
        word_count=word_count,
        sentence_count=sentence_count,
        paragraph_count=paragraph_count,
        link_count=link_count,
        link_density=link_density,
        heuristic=heuristic,
        hints=hints,
        path_label=path_label,
    )


def _heuristic_document_guess(
    *,
    path: str,
    title_lower: str,
    word_count: int,
    sentence_count: int,
    paragraph_count: int,
    link_count: int,
    link_density: float,
) -> DocumentClassification:
    if _path_has_collection_marker(path) or _title_has_marker(title_lower, COLLECTION_TITLE_MARKERS):
        return DocumentClassification(DocumentType.COLLECTION.value, "collection path/title marker")
    if _is_root_path(path):
        return DocumentClassification(DocumentType.PROFILE.value, "root homepage")
    if _path_has_marker(path, PROFILE_PATH_MARKERS) or (
        _title_has_marker(title_lower, PROFILE_TITLE_MARKERS) and word_count < 1200
    ):
        return DocumentClassification(DocumentType.PROFILE.value, "profile path/title marker")
    if _path_has_marker(path, REFERENCE_PATH_MARKERS) or _title_has_marker(title_lower, REFERENCE_TITLE_MARKERS):
        return DocumentClassification(DocumentType.REFERENCE.value, "reference path/title marker")
    if link_count >= 20 and word_count < 180:
        return DocumentClassification(DocumentType.COLLECTION.value, "many links with limited prose")
    if link_density >= 4.0 and paragraph_count <= 2 and word_count < 300:
        return DocumentClassification(DocumentType.COLLECTION.value, "high link density")
    if sentence_count < 6 and word_count < 500:
        return DocumentClassification(DocumentType.IGNORE.value, "limited sentence-level prose")
    return DocumentClassification(DocumentType.ESSAY.value, f"substantive prose: {word_count} words")


def _page_hints(*, path: str, title_lower: str, word_count: int) -> list[str]:
    hints: list[str] = []
    if _is_root_path(path):
        hints.append("root homepage: often profile/home, but decide from actual content")
    if _path_has_collection_marker(path) or _title_has_marker(title_lower, COLLECTION_TITLE_MARKERS):
        hints.append("collection marker in path/title: could be archive/books/links, but inspect content")
    if _path_has_marker(path, PROFILE_PATH_MARKERS) or (
        _title_has_marker(title_lower, PROFILE_TITLE_MARKERS) and word_count < 1200
    ):
        hints.append("profile marker in path/title: could be about/contact/CV/homepage")
    if _path_has_marker(path, REFERENCE_PATH_MARKERS) or _title_has_marker(title_lower, REFERENCE_TITLE_MARKERS):
        hints.append("reference marker in path/title: could be docs/legal/reference")
    return hints


def _path_label(path: str) -> str | None:
    clean = path.strip("/")
    if not clean or "/" in clean:
        return None
    label = re.sub(r"[-_]+", " ", clean).strip()
    if not label:
        return None
    return label.title()


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


def _is_root_path(path: str) -> bool:
    return (path.rstrip("/") or "/") == "/"


def _path_has_collection_marker(path: str) -> bool:
    clean = path.rstrip("/") or "/"
    if clean in COLLECTION_EXACT_PATH_MARKERS:
        return True
    return _path_has_marker(path, COLLECTION_PREFIX_PATH_MARKERS)


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


def _analyze_document_with_llm(
    *,
    url: str,
    metadata_title: str | None,
    text: str,
    word_count: int,
    sentence_count: int,
    paragraph_count: int,
    link_count: int,
    link_density: float,
    heuristic: DocumentClassification,
    hints: list[str],
    path_label: str | None,
) -> DocumentAnalysis:
    key = require_openai_api_key(f"document analysis ({url})")
    payload = _document_analysis_payload(
        url=url,
        metadata_title=metadata_title,
        text=text,
        word_count=word_count,
        sentence_count=sentence_count,
        paragraph_count=paragraph_count,
        link_count=link_count,
        link_density=link_density,
        heuristic=heuristic,
        hints=hints,
        path_label=path_label,
    )
    with httpx.Client(timeout=DOCUMENT_CLASSIFIER_TIMEOUT_SECONDS) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    return _parse_document_analysis_response_data(
        response.json(),
        metadata_title=metadata_title,
        fallback_text=text,
    )


async def analyze_document_async(
    *,
    url: str,
    metadata_title: str | None,
    text: str,
    link_count: int,
    has_author: bool = False,
    has_published_date: bool = False,
) -> DocumentAnalysis:
    """Analyze extracted document text using the async OpenAI path."""
    words = re.findall(r"\w+", text)
    word_count = len(words)
    sentence_count = len(re.findall(r"[.!?](?:\s|$)", text))
    paragraph_count = len([part for part in re.split(r"\n{2,}", text.strip()) if len(part.split()) >= 8])
    title_lower = (metadata_title or "").lower()
    combined_text = f"{metadata_title or ''}\n{text}"
    path = urlparse(url).path.lower()
    path_label = _path_label(path)
    link_density = link_count / max(word_count / 100.0, 1.0)

    if looks_non_english(combined_text):
        return _fallback_analysis(metadata_title, text, DocumentType.IGNORE.value)

    if _looks_like_gambling_spam(combined_text):
        return _fallback_analysis(metadata_title, text, DocumentType.IGNORE.value)

    heuristic = _heuristic_document_guess(
        path=path,
        title_lower=title_lower,
        word_count=word_count,
        sentence_count=sentence_count,
        paragraph_count=paragraph_count,
        link_count=link_count,
        link_density=link_density,
    )
    hints = _page_hints(path=path, title_lower=title_lower, word_count=word_count)
    key = require_openai_api_key(f"document analysis ({url})")
    payload = _document_analysis_payload(
        url=url,
        metadata_title=metadata_title,
        text=text,
        word_count=word_count,
        sentence_count=sentence_count,
        paragraph_count=paragraph_count,
        link_count=link_count,
        link_density=link_density,
        heuristic=heuristic,
        hints=hints,
        path_label=path_label,
    )
    async with httpx.AsyncClient(timeout=DOCUMENT_CLASSIFIER_TIMEOUT_SECONDS) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
    return _parse_document_analysis_response_data(
        response.json(),
        metadata_title=metadata_title,
        fallback_text=text,
    )


def _document_analysis_payload(
    *,
    url: str,
    metadata_title: str | None,
    text: str,
    word_count: int,
    sentence_count: int,
    paragraph_count: int,
    link_count: int,
    link_density: float,
    heuristic: DocumentClassification,
    hints: list[str],
    path_label: str | None,
) -> dict[str, object]:
    """Build the Responses API payload for document analysis."""
    text_start_lines = _text_start_lines(text)
    excerpt = _analysis_excerpt(text=text, heuristic=heuristic, text_start_lines=text_start_lines)
    return {
        "model": DOCUMENT_CLASSIFIER_MODEL,
        "instructions": (
            "Analyze a crawled web page for Iris, a corpus of substantive written thought. "
            "Choose the specific page/article title, not the generic site title. metadata_title may be stale "
            "or wrong from an earlier crawl; do not trust it over URL and page structure. "
            "For title, remove site or author prefixes/suffixes such as 'Title · Site Name', "
            "'Title - Author Name', 'Site Name | Title', or 'Title — Blog Name'; for example, "
            "return 'Advice', not 'Advice · Patrick Collison'. "
            "For collection pages, use the collection page's own label or heading, such as 'Blog', "
            "'Bookshelf', 'Links', 'Travel', or 'Writing'. Do not use the title of the first linked post, "
            "first excerpt, or most prominent child item as the collection title. If document_type is collection "
            "and candidate_collection_title is present, the title must be candidate_collection_title unless a "
            "clearer parent collection heading is visible. "
            "Single-segment paths like /blog, /archive, /links, /bookshelf, /travel, or /writing usually name "
            "collection pages unless the content is clearly one standalone article. If a collection embeds or "
            "previews a full child post, still classify the parent page as collection and title it from the "
            "parent page label or heading. Use text_start_lines to identify nav/page labels before child content. "
            "Write a slightly more comprehensive 2-4 sentence summary in a lively, descriptive voice: specific, "
            "slightly playful, and useful for recognizing the piece later. Avoid bland labels like "
            "'This article discusses...'. Name the central move, tension, or unusual angle when visible. "
            "Preserve concrete biographical or affiliation signals when they are explicit, such as schools, "
            "employers, cities, roles, programs, projects, or first-person experience with an institution. Examples: "
            "'A cranky but practical note arguing that slow meetings are a tax on momentum, with a bias toward shipping and apologizing later.' "
            "'A personal field report from burnout country: what broke, what helped, and why productivity advice can become its own little trap.' "
            "'A link-heavy map of the author's favorite tools and reading trails, more cabinet of curiosities than polished essay.' "
            "Return 3-8 short semantic topics, not raw keyword spam. "
            "Choose category_slug from this one-word list: ai, software, work, productivity, rationality, "
            "philosophy, money, philanthropy, health, dating, culture, politics, history, science, personal, "
            "writing, fiction, education. Use null only if the page is ignore/reference/profile and no useful "
            "content category applies. "
            "Use document_type values only from: essay, collection, profile, reference, ignore. "
            "essay means a standalone substantive written piece, including personal opinions, book reports, "
            "media reviews, or analytical posts. collection means an index/archive/link list/anthology page, "
            "or any page whose main purpose is to list, group, preview, or route to multiple posts, essays, "
            "blogs, categories, books, notes, or external works. If a page contains multiple distinct posts "
            "or multiple blog sections, classify it as collection even when it has substantial excerpts. "
            "profile means about/contact/CV/homepage biography. reference means docs/legal/reference material. "
            "ignore means too thin, spam, non-English, or not useful written content. "
            "Before returning: if document_type is collection and candidate_collection_title is present, "
            "set title exactly to candidate_collection_title unless the page has a clearer parent collection heading. "
            "Return the requested fields according to the provided schema."
        ),
        "input": json.dumps(
            {
                "url": url,
                "metadata_title": metadata_title,
                "word_count": word_count,
                "sentence_count": sentence_count,
                "paragraph_count": paragraph_count,
                "link_count": link_count,
                "link_density": round(link_density, 3),
                "url_path_label": path_label,
                "candidate_collection_title": path_label,
                "page_hints": hints,
                "text_start_lines": text_start_lines,
                "heuristic": {
                    "document_type": heuristic.document_type,
                    "reason": heuristic.reason,
                },
                "excerpt": excerpt,
            },
            ensure_ascii=False,
        ),
        "reasoning": {"effort": "minimal"},
        "text": {"format": _document_analysis_response_format(), "verbosity": "low"},
        "max_output_tokens": 1200,
        "store": False,
    }


def _parse_document_analysis_response_data(
    data: Mapping[str, object],
    *,
    metadata_title: str | None,
    fallback_text: str,
) -> DocumentAnalysis:
    """Parse a Responses API payload into normalized document analysis."""
    if data.get("status") == "incomplete":
        reason = data.get("incomplete_details") or {}
        raise RuntimeError(f"document classifier response incomplete: {reason}")
    text_out = data.get("output_text") or _response_output_text(data)
    if not text_out.strip():
        raise ValueError("document classifier response did not include output text")
    parsed = _parse_document_analysis_response(text_out)
    return DocumentAnalysis(
        title=_normalize_title(parsed.get("title"), fallback=metadata_title),
        summary=_normalize_summary(parsed.get("summary"), fallback=fallback_text),
        topics=_normalize_topics(parsed.get("topics")),
        category_slug=_normalize_category_slug(parsed.get("category_slug")),
        document_type=_normalize_document_type(parsed.get("document_type")),
    )


def _parse_document_analysis_response(text: str) -> Mapping[str, object]:
    """Parse structured output, falling back to JSON extraction for old responses."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = json.loads(_extract_json_object(text))
    if not isinstance(parsed, dict):
        raise ValueError("document classifier response was not a JSON object")
    return parsed


def _fallback_analysis(metadata_title: str | None, text: str, document_type: str) -> DocumentAnalysis:
    return DocumentAnalysis(
        title=metadata_title,
        summary=_fallback_summary(text),
        topics=[],
        category_slug=None,
        document_type=document_type,
    )


def _text_start_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        lines.append(line[:160])
        if len(lines) >= 40:
            break
    return lines


def _analysis_excerpt(*, text: str, heuristic: DocumentClassification, text_start_lines: list[str]) -> str:
    if heuristic.document_type == DocumentType.COLLECTION.value:
        return "\n".join(text_start_lines[:20])[:1600]
    return re.sub(r"\s+", " ", text).strip()[:6000]


def _fallback_summary(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    return " ".join(sentences[:3]).strip()[:700]


def _normalize_title(value: object, *, fallback: str | None) -> str | None:
    title = str(value or "").strip()
    if not title:
        return fallback
    return title[:300]


def _normalize_summary(value: object, *, fallback: str) -> str:
    summary = str(value or "").strip()
    if not summary:
        summary = _fallback_summary(fallback)
    return summary[:1000]


def _normalize_topics(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    topics: list[str] = []
    seen: set[str] = set()
    for item in value:
        topic = re.sub(r"\s+", " ", str(item or "").strip().lower())
        if not topic or topic in seen:
            continue
        topics.append(topic[:80])
        seen.add(topic)
        if len(topics) >= 8:
            break
    return topics


def _normalize_category_slug(value: object) -> str | None:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    if slug in DOCUMENT_CATEGORY_SLUGS:
        return slug
    return None


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
        raise ValueError("document classifier response did not contain JSON")
    return match.group(0)
