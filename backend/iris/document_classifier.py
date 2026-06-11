from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from iris.language import looks_non_english


@dataclass(frozen=True)
class DocumentClassification:
    document_type: str
    quality_score: float
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
        return DocumentClassification("ignore", 0.02, 0.95, "primarily non-English text")

    if _looks_like_gambling_spam(combined_text):
        return DocumentClassification("ignore", 0.02, 0.95, "casino/betting spam content")

    if _path_has_marker(path, REFERENCE_PATH_MARKERS) or _title_has_marker(title_lower, REFERENCE_TITLE_MARKERS):
        return DocumentClassification("reference", 0.15, 0.85, "reference/docs/legal marker")

    if _path_has_marker(path, PROFILE_PATH_MARKERS) or (
        _title_has_marker(title_lower, PROFILE_TITLE_MARKERS) and word_count < 1200
    ):
        return DocumentClassification("profile", 0.25, 0.75, "profile/about marker")

    if _path_has_marker(path, COLLECTION_PATH_MARKERS) or _title_has_marker(title_lower, COLLECTION_TITLE_MARKERS):
        if link_count >= 5 or link_density >= 1.2 or word_count < 900:
            return DocumentClassification("collection", 0.35, 0.85, "collection path/title marker")

    if link_count >= 20 and word_count < 180:
        return DocumentClassification("collection", 0.35, 0.85, "many links with limited prose")

    if link_density >= 4.0 and paragraph_count <= 2 and word_count < 300:
        return DocumentClassification("collection", 0.35, 0.75, "high link density")

    if word_count < 80:
        return DocumentClassification("ignore", 0.05, 0.95, f"too short: {word_count} words")

    if sentence_count < 6 and word_count < 500:
        return DocumentClassification("ignore", 0.15, 0.7, "not enough sentence-level prose")

    quality = min(1.0, 0.32 + (word_count / 2200))
    if paragraph_count >= 4:
        quality += 0.08
    if has_author:
        quality += 0.04
    if has_published_date:
        quality += 0.04
    if link_density > 1.5:
        quality -= 0.08
    quality = max(0.2, min(1.0, quality))
    confidence = 0.65
    if word_count >= 700 and sentence_count >= 10:
        confidence = 0.85
    return DocumentClassification("essay", quality, confidence, f"substantive prose: {word_count} words")


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
