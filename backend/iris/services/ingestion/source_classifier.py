from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping

import httpx
from bs4 import BeautifulSoup

from iris.schemas.enums import SourceStatus
from iris.schemas.ingestion import SourceClassification, SourceClassifierResult
from iris.services.common.config import SOURCE_CLASSIFIER_MODEL, SOURCE_CLASSIFIER_TIMEOUT_SECONDS, require_openai_api_key
from iris.services.common.language import looks_non_english
from iris.services.common.url_utils import domain_for_url, normalize_url

logger = logging.getLogger("iris.source_classifier")


OBVIOUS_IGNORED_EXACT_DOMAINS: dict[str, str] = {
    "youtube.com": "video platform",
    "youtu.be": "video platform",
    "vimeo.com": "video platform",
    "wikipedia.org": "reference site",
    "wikidata.org": "reference site",
    "wikimedia.org": "reference site",
    "twitter.com": "social platform",
    "x.com": "social platform",
    "facebook.com": "social platform",
    "instagram.com": "social platform",
    "tiktok.com": "social platform",
    "linkedin.com": "social platform",
    "reddit.com": "social platform",
    "github.com": "code host",
    "gitlab.com": "code host",
    "bitbucket.org": "code host",
    "amazon.com": "commerce site",
    "amzn.to": "commerce site",
    "goodreads.com": "catalog site",
    "medium.com": "publishing platform root",
    "substack.com": "publishing platform root",
    "wordpress.com": "publishing platform root",
    "blogger.com": "publishing platform root",
    "wp.me": "publishing platform root",
    "subscribe.wordpress.com": "publishing platform root",
    "arxiv.org": "reference site",
    "books.google.com": "reference site",
    "ideas.repec.org": "reference site",
    "jstor.org": "reference site",
    "nytimes.com": "mainstream publication",
    "washingtonpost.com": "mainstream publication",
    "wsj.com": "mainstream publication",
    "theguardian.com": "mainstream publication",
    "theatlantic.com": "mainstream publication",
    "newyorker.com": "mainstream publication",
    "vox.com": "mainstream publication",
    "bloomberg.com": "mainstream publication",
    "reuters.com": "mainstream publication",
    "apnews.com": "mainstream publication",
    "nature.com": "publication/reference site",
    "slate.com": "mainstream publication",
    "economist.com": "mainstream publication",
    "tandfonline.com": "publication/reference site",
    "flickr.com": "media platform",
}

OBVIOUS_IGNORED_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".youtube.com", "video platform"),
    (".wikipedia.org", "reference site"),
    (".wikidata.org", "reference site"),
    (".wikimedia.org", "reference site"),
    (".twitter.com", "social platform"),
    (".x.com", "social platform"),
    (".facebook.com", "social platform"),
    (".instagram.com", "social platform"),
    (".tiktok.com", "social platform"),
    (".linkedin.com", "social platform"),
    (".reddit.com", "social platform"),
    (".github.com", "code host"),
    (".gitlab.com", "code host"),
    (".amazon.com", "commerce site"),
    (".nytimes.com", "mainstream publication"),
    (".washingtonpost.com", "mainstream publication"),
    (".theguardian.com", "mainstream publication"),
    (".medium.com", "publishing platform"),
    (".wordpress.com", "publishing platform"),
    (".blogger.com", "publishing platform"),
    (".arxiv.org", "reference site"),
    (".books.google.com", "reference site"),
    (".ideas.repec.org", "reference site"),
    (".jstor.org", "reference site"),
    (".nature.com", "publication/reference site"),
    (".slate.com", "mainstream publication"),
    (".economist.com", "mainstream publication"),
    (".tandfonline.com", "publication/reference site"),
    (".flickr.com", "media platform"),
)

PERSONAL_PLATFORM_SUFFIXES: tuple[str, ...] = (
    ".substack.com",
    ".github.io",
    ".wordpress.com",
    ".blogspot.com",
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

WRITING_SECTION_MARKERS: tuple[str, ...] = (
    "blog",
    "essays",
    "notes",
    "posts",
    "writing",
    "writings",
)


def classify_source_url(url: str) -> SourceClassification:
    domain = domain_for_url(normalize_url(url))
    if not domain:
        return SourceClassification(status=SourceStatus.IGNORED.value, reason="missing domain")

    for suffix in PERSONAL_PLATFORM_SUFFIXES:
        if domain.endswith(suffix) and domain != suffix.lstrip("."):
            return SourceClassification(status=SourceStatus.QUEUED.value, reason=f"personal platform suffix {suffix}")

    if domain in OBVIOUS_IGNORED_EXACT_DOMAINS:
        reason = OBVIOUS_IGNORED_EXACT_DOMAINS[domain]
        return SourceClassification(status=SourceStatus.IGNORED.value, reason=f"blocked exact domain {domain}: {reason}")

    for suffix, reason in OBVIOUS_IGNORED_SUFFIXES:
        if domain.endswith(suffix):
            return SourceClassification(status=SourceStatus.IGNORED.value, reason=f"blocked domain suffix {suffix}: {reason}")

    return SourceClassification(status=SourceStatus.QUEUED.value, reason="candidate written source")


def classify_source_homepage(url: str, html: str) -> SourceClassification:
    domain = domain_for_url(normalize_url(url))
    if domain.endswith(".test"):
        return SourceClassification(status=SourceStatus.QUEUED.value, reason="test fixture domain")

    obvious = classify_source_url(url)
    if obvious.status == SourceStatus.IGNORED.value:
        return obvious

    homepage_context = _homepage_context(html)
    if not homepage_context.strip():
        raise ValueError(f"Cannot classify source homepage with no readable text: {url}")
    if looks_non_english(homepage_context):
        return SourceClassification(
            status=SourceStatus.IGNORED.value,
            reason="homepage appears to be primarily non-English text",
        )

    if _looks_like_professional_service_site(homepage_context):
        return SourceClassification(
            status=SourceStatus.IGNORED.value,
            reason="professional service/clinic site, not a personal blog or essay archive",
        )
    if _looks_like_gambling_spam_site(homepage_context):
        return SourceClassification(
            status=SourceStatus.IGNORED.value,
            reason="casino/betting spam or gambling SEO content, not personal essays",
        )
    key = require_openai_api_key(f"source homepage classification ({url})")

    try:
        result = _classify_with_openai(key, url, homepage_context)
        return _normalize_llm_result(result)
    except Exception as exc:
        logger.warning("Homepage source classifier failed for %s: %s", url, exc)
        raise


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


def _has_writing_section_link(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a"):
        text = anchor.get_text(" ", strip=True).lower()
        href = str(anchor.get("href") or "").lower().strip("/")
        if text in WRITING_SECTION_MARKERS or href in WRITING_SECTION_MARKERS:
            return True
        if any(href.startswith(f"{marker}/") for marker in WRITING_SECTION_MARKERS):
            return True
    return False


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


def _classify_with_openai(api_key: str, url: str, homepage_context: str) -> SourceClassifierResult:
    """Classify a source homepage with structured LLM output."""
    payload = {
        "model": SOURCE_CLASSIFIER_MODEL,
        "instructions": (
            "Classify whether Iris should crawl this source. Iris wants personal opinions, personal blogs, "
            "single-author or small-group essay archives, independent writing, newsletters, and substantive "
            "written thought. ACCEPT personal homepages/blogs even if they are messy, old-school, link-heavy, "
            "or casual, as long as they appear to contain authored posts/essays by an individual or small group. "
            "ACCEPT individual creator newsletter subdomains on platforms like Substack when the homepage appears "
            "to be an authored archive of posts/essays; do not reject those merely because they use a publishing "
            "platform. Reject the platform root and corporate/product newsletters. "
            "Reject broad multi-user platforms, reference sites, video/social networks, commerce, docs, code hosts, "
            "corporate blogs, content marketing, customer stories, product pages, generic company/product sites, "
            "and mainstream publications unless the homepage is clearly an individual author's essay archive. "
            "A company having a blog, resources, writing, or news section is not enough; reject it unless the "
            "source is primarily personal or independent authored thought. "
            "Keep reason concise: one sentence, under 20 words. "
            "Return the requested fields according to the provided schema."
        ),
        "input": f"URL: {url}\n\nHomepage text:\n{homepage_context}",
        "text": {"format": _source_classifier_response_format(), "verbosity": "low"},
        "max_output_tokens": 2000,
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
    if data.get("status") == "incomplete":
        reason = data.get("incomplete_details") or {}
        raise RuntimeError(f"source classifier response incomplete: {reason}")
    text = data.get("output_text") or _response_output_text(data)
    if not text:
        raise ValueError("empty classifier response")
    return _parse_classifier_json(text)


def _source_classifier_response_format() -> dict[str, object]:
    """Return the structured-output schema for source homepage classification."""
    return {
        "type": "json_schema",
        "name": "source_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "should_crawl": {"type": "boolean"},
                "reason": {"type": "string", "maxLength": 240},
            },
            "required": ["should_crawl", "reason"],
        },
    }


def _parse_classifier_json(text: str) -> SourceClassifierResult:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("classifier JSON was not an object")
    return SourceClassifierResult(
        should_crawl=bool(payload.get("should_crawl")),
        reason=str(payload.get("reason") or "LLM source classification").strip()[:1000],
    )


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


def _normalize_llm_result(result: SourceClassifierResult | Mapping[str, object]) -> SourceClassification:
    """Convert a raw or parsed LLM classification into source status."""
    if isinstance(result, Mapping):
        result = SourceClassifierResult(
            should_crawl=bool(result.get("should_crawl")),
            reason=str(result.get("reason") or "LLM source classification").strip()[:1000],
        )
    return SourceClassification(
        status=SourceStatus.QUEUED.value if result.should_crawl else SourceStatus.IGNORED.value,
        reason=result.reason,
    )
