from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from iris.config import SOURCE_CLASSIFIER_MODEL, SOURCE_CLASSIFIER_TIMEOUT_SECONDS, openai_api_key
from iris.language import looks_non_english
from iris.url_utils import domain_for_url, normalize_url

logger = logging.getLogger("iris.source_classifier")


@dataclass(frozen=True)
class SourceClassification:
    source_type: str
    status: str
    reason: str
    confidence: float | None = None


OBVIOUS_IGNORED_EXACT_DOMAINS: dict[str, str] = {
    "youtube.com": "video_platform",
    "youtu.be": "video_platform",
    "vimeo.com": "video_platform",
    "wikipedia.org": "reference",
    "wikidata.org": "reference",
    "wikimedia.org": "reference",
    "twitter.com": "social",
    "x.com": "social",
    "facebook.com": "social",
    "instagram.com": "social",
    "tiktok.com": "social",
    "linkedin.com": "social",
    "reddit.com": "social",
    "github.com": "code_host",
    "gitlab.com": "code_host",
    "bitbucket.org": "code_host",
    "amazon.com": "commerce",
    "amzn.to": "commerce",
    "goodreads.com": "catalog",
    "medium.com": "publishing_platform",
    "substack.com": "publishing_platform",
    "wordpress.com": "publishing_platform",
    "blogger.com": "publishing_platform",
    "wp.me": "publishing_platform",
    "subscribe.wordpress.com": "publishing_platform",
    "arxiv.org": "reference",
    "books.google.com": "reference",
    "ideas.repec.org": "reference",
    "jstor.org": "reference",
    "nytimes.com": "publication",
    "washingtonpost.com": "publication",
    "wsj.com": "publication",
    "theguardian.com": "publication",
    "theatlantic.com": "publication",
    "newyorker.com": "publication",
    "vox.com": "publication",
    "bloomberg.com": "publication",
    "reuters.com": "publication",
    "apnews.com": "publication",
    "nature.com": "publication",
    "slate.com": "publication",
    "economist.com": "publication",
    "tandfonline.com": "publication",
    "flickr.com": "media_platform",
}

OBVIOUS_IGNORED_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".youtube.com", "video_platform"),
    (".wikipedia.org", "reference"),
    (".wikidata.org", "reference"),
    (".wikimedia.org", "reference"),
    (".twitter.com", "social"),
    (".x.com", "social"),
    (".facebook.com", "social"),
    (".instagram.com", "social"),
    (".tiktok.com", "social"),
    (".linkedin.com", "social"),
    (".reddit.com", "social"),
    (".github.com", "code_host"),
    (".gitlab.com", "code_host"),
    (".amazon.com", "commerce"),
    (".nytimes.com", "publication"),
    (".washingtonpost.com", "publication"),
    (".theguardian.com", "publication"),
    (".medium.com", "publishing_platform"),
    (".wordpress.com", "publishing_platform"),
    (".blogger.com", "publishing_platform"),
    (".arxiv.org", "reference"),
    (".books.google.com", "reference"),
    (".ideas.repec.org", "reference"),
    (".jstor.org", "reference"),
    (".nature.com", "publication"),
    (".slate.com", "publication"),
    (".economist.com", "publication"),
    (".tandfonline.com", "publication"),
    (".flickr.com", "media_platform"),
)

PERSONAL_PLATFORM_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".substack.com", "newsletter"),
    (".github.io", "personal_site"),
    (".wordpress.com", "personal_site"),
    (".blogspot.com", "personal_site"),
)

PROFESSIONAL_SERVICE_MARKERS: tuple[str, ...] = (
    "appointment",
    "appointments",
    "book a consultation",
    "clinic",
    "clinician",
    "insurance",
    "patient",
    "patients",
    "practice",
    "psychiatry",
    "psychologist",
    "psychology",
    "schedule a consultation",
    "services",
    "telehealth",
    "therapy",
    "therapist",
    "treatment",
)

SPAM_GAMBLING_MARKERS: tuple[str, ...] = (
    "betting",
    "casino",
    "gambling",
    "sportsbook",
    "토토",
    "먹튀",
    "카지노",
)


def classify_source_url(url: str) -> SourceClassification:
    domain = domain_for_url(normalize_url(url))
    if not domain:
        return SourceClassification(source_type="unknown", status="ignored", reason="missing domain")

    for suffix, source_type in PERSONAL_PLATFORM_SUFFIXES:
        if domain.endswith(suffix) and domain != suffix.lstrip("."):
            return SourceClassification(source_type=source_type, status="queued", reason=f"personal platform suffix {suffix}")

    if domain in OBVIOUS_IGNORED_EXACT_DOMAINS:
        source_type = OBVIOUS_IGNORED_EXACT_DOMAINS[domain]
        return SourceClassification(source_type=source_type, status="ignored", reason=f"blocked exact domain {domain}")

    for suffix, source_type in OBVIOUS_IGNORED_SUFFIXES:
        if domain.endswith(suffix):
            return SourceClassification(source_type=source_type, status="ignored", reason=f"blocked domain suffix {suffix}")

    return SourceClassification(source_type="unknown", status="queued", reason="candidate written source")


def classify_source_homepage(url: str, html: str) -> SourceClassification:
    domain = domain_for_url(normalize_url(url))
    if domain.endswith(".test"):
        return SourceClassification(source_type="unknown", status="queued", reason="test fixture domain", confidence=None)

    obvious = classify_source_url(url)
    if obvious.status == "ignored":
        return obvious

    homepage_context = _homepage_context(html)
    if not homepage_context.strip():
        return SourceClassification(source_type="unknown", status="queued", reason="empty homepage text", confidence=None)
    if looks_non_english(homepage_context):
        return SourceClassification(
            source_type="non_english",
            status="ignored",
            reason="homepage appears to be primarily non-English text",
            confidence=0.9,
        )
    if obvious.source_type in {"newsletter", "personal_site"}:
        return obvious

    key = openai_api_key()
    if not key:
        return SourceClassification(
            source_type="unknown",
            status="queued",
            reason="no OpenAI API key available; defaulting to queueable candidate",
            confidence=None,
        )

    if _looks_like_professional_service_site(homepage_context):
        return SourceClassification(
            source_type="professional_service",
            status="ignored",
            reason="professional service/clinic site, not a personal blog or essay archive",
            confidence=0.9,
        )
    if _looks_like_gambling_spam_site(homepage_context):
        return SourceClassification(
            source_type="spam_gambling",
            status="ignored",
            reason="casino/betting spam or gambling SEO content, not personal essays",
            confidence=0.95,
        )

    try:
        result = _classify_with_openai(key, url, homepage_context)
        return _normalize_llm_result(result)
    except Exception as exc:
        logger.warning("Homepage source classifier failed for %s: %s", url, exc)
        return SourceClassification(
            source_type="unknown",
            status="queued",
            reason=f"classifier failed; defaulting to queueable candidate: {exc}",
            confidence=None,
        )


def _homepage_context(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    parts: list[str] = []
    title = soup.find("title")
    if title and title.get_text(strip=True):
        parts.append(f"TITLE: {title.get_text(' ', strip=True)}")
    for meta_name in ("description", "og:description", "twitter:description"):
        tag = soup.find("meta", attrs={"name": meta_name}) or soup.find("meta", attrs={"property": meta_name})
        content = tag.get("content") if tag else None
        if content:
            parts.append(f"META {meta_name}: {content}")
    for selector in ("h1", "h2", "nav", "main", "article", "body"):
        for tag in soup.select(selector)[:8]:
            text = tag.get_text(" ", strip=True)
            if text:
                parts.append(text)
    context = "\n".join(dict.fromkeys(parts))
    return re.sub(r"\s+", " ", context)[:12000]


def _looks_like_professional_service_site(homepage_context: str) -> bool:
    text = homepage_context.lower()
    marker_count = sum(1 for marker in PROFESSIONAL_SERVICE_MARKERS if marker in text)
    has_business_action = any(marker in text for marker in ("appointment", "book a consultation", "schedule a consultation"))
    has_healthcare = any(marker in text for marker in ("clinic", "psychiatry", "psychologist", "therapy", "therapist", "treatment"))
    has_service_language = any(marker in text for marker in ("services", "patients", "insurance", "practice"))
    return marker_count >= 4 and (has_business_action or (has_healthcare and has_service_language))


def _looks_like_gambling_spam_site(homepage_context: str) -> bool:
    text = homepage_context.lower()
    marker_hits = sum(1 for marker in SPAM_GAMBLING_MARKERS if marker in text)
    if marker_hits >= 2:
        return True
    spam_repetition = len(re.findall(r"(먹튀|카지노|토토)", homepage_context))
    return spam_repetition >= 3


def _classify_with_openai(api_key: str, url: str, homepage_context: str) -> dict:
    payload = {
        "model": SOURCE_CLASSIFIER_MODEL,
        "instructions": (
            "Classify whether Iris should crawl this source. Iris wants personal opinions, personal blogs, "
            "single-author or small-group essay archives, independent writing, newsletters, and substantive "
            "written thought. ACCEPT personal homepages/blogs even if they are messy, old-school, link-heavy, "
            "or casual, as long as they appear to contain authored posts/essays by an individual or small group. "
            "Reject broad multi-user platforms, reference sites, video/social networks, commerce, docs, code hosts, "
            "generic company/product sites, and mainstream publications unless the homepage is clearly an "
            "individual author's essay archive. "
            "Return JSON only with keys: should_crawl boolean, source_type string, confidence number 0-1, reason string."
        ),
        "input": f"URL: {url}\n\nHomepage text:\n{homepage_context}",
        "max_output_tokens": 240,
        "store": False,
    }
    with httpx.Client(timeout=SOURCE_CLASSIFIER_TIMEOUT_SECONDS) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    text = data.get("output_text") or _response_output_text(data)
    if not text:
        raise ValueError("empty classifier response")
    return json.loads(_extract_json_object(text))


def _response_output_text(data: dict) -> str:
    chunks: list[str] = []
    for item in data.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks)


def _extract_json_object(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("classifier response did not contain JSON")
    return match.group(0)


def _normalize_llm_result(result: dict) -> SourceClassification:
    should_crawl = bool(result.get("should_crawl"))
    source_type = str(result.get("source_type") or ("unknown" if should_crawl else "non_target")).strip()[:40]
    reason = str(result.get("reason") or "LLM source classification").strip()[:1000]
    try:
        confidence = float(result.get("confidence"))
    except (TypeError, ValueError):
        confidence = None
    return SourceClassification(
        source_type=source_type or "unknown",
        status="queued" if should_crawl else "ignored",
        reason=reason,
        confidence=confidence,
    )
