from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

from iris.models import SourceStatus
from iris.services.common.config import SOURCE_CLASSIFIER_MODEL, SOURCE_CLASSIFIER_TIMEOUT_SECONDS, require_openai_api_key
from iris.services.common.language import looks_non_english
from iris.services.common.url_utils import domain_for_url, normalize_url

logger = logging.getLogger("iris.source_classifier")


@dataclass(frozen=True)
class SourceClassification:
    status: str
    reason: str
    confidence: float | None = None


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
        return SourceClassification(status=SourceStatus.QUEUED.value, reason="test fixture domain", confidence=None)

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
            confidence=0.9,
        )

    if _looks_like_professional_service_site(homepage_context):
        return SourceClassification(
            status=SourceStatus.IGNORED.value,
            reason="professional service/clinic site, not a personal blog or essay archive",
            confidence=0.9,
        )
    if _looks_like_gambling_spam_site(homepage_context):
        return SourceClassification(
            status=SourceStatus.IGNORED.value,
            reason="casino/betting spam or gambling SEO content, not personal essays",
            confidence=0.95,
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
            "Return JSON only with keys: should_crawl boolean, confidence number 0-1, reason string."
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
    reason = str(result.get("reason") or "LLM source classification").strip()[:1000]
    try:
        confidence = float(result.get("confidence"))
    except (TypeError, ValueError):
        confidence = None
    return SourceClassification(
        status=SourceStatus.QUEUED.value if should_crawl else SourceStatus.IGNORED.value,
        reason=reason,
        confidence=confidence,
    )
