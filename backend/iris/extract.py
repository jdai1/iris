from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from iris.document_classifier import classify_document


@dataclass(frozen=True)
class ExtractedLink:
    url: str
    anchor_text: str
    context: str


@dataclass(frozen=True)
class ExtractedPage:
    title: str | None
    author: str | None
    published_at: datetime | None
    text: str
    summary: str
    topics: list[str]
    document_type: str
    quality_score: float
    links: list[ExtractedLink]


BOILERPLATE_SELECTORS = [
    "script",
    "style",
    "noscript",
    "svg",
    "header",
    "nav",
    "footer",
    "form",
    "aside",
]


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if tag and tag.get("content"):
            return str(tag["content"]).strip()
    return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed:
            return parsed
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _summarize(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    summary = " ".join(sentences[:3]).strip()
    return summary[:700]


def _topics(text: str, title: str | None) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", f"{title or ''} {text}".lower())
    stop = {
        "about",
        "after",
        "also",
        "because",
        "before",
        "being",
        "between",
        "could",
        "first",
        "from",
        "have",
        "into",
        "more",
        "other",
        "people",
        "some",
        "than",
        "that",
        "their",
        "there",
        "these",
        "they",
        "this",
        "what",
        "when",
        "where",
        "which",
        "with",
        "would",
        "your",
    }
    counts: dict[str, int] = {}
    for word in words:
        if word in stop:
            continue
        counts[word] = counts.get(word, 0) + 1
    return [word for word, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:8]]


def extract_page(html: str, final_url: str) -> ExtractedPage:
    soup = BeautifulSoup(html, "html.parser")
    title = _meta(soup, "og:title", "twitter:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    author = _meta(soup, "author", "article:author", "twitter:creator")
    published_at = _parse_date(
        _meta(soup, "article:published_time", "date", "pubdate", "datePublished")
    )

    links: list[ExtractedLink] = []
    for tag in soup.find_all("a", href=True):
        anchor = tag.get_text(" ", strip=True)
        href = urljoin(final_url, str(tag["href"]))
        parent_text = tag.parent.get_text(" ", strip=True) if tag.parent else anchor
        links.append(ExtractedLink(url=href, anchor_text=anchor[:500], context=parent_text[:1000]))

    for selector in BOILERPLATE_SELECTORS:
        for tag in soup.select(selector):
            tag.decompose()

    article = soup.find("article") or soup.find("main") or soup.body or soup
    content_link_count = len(article.find_all("a", href=True))
    text = article.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    summary = _summarize(text)
    topics = _topics(text, title)
    classification = classify_document(
        url=final_url,
        title=title,
        text=text,
        link_count=content_link_count,
        has_author=bool(author),
        has_published_date=bool(published_at),
    )
    return ExtractedPage(
        title=title,
        author=author,
        published_at=published_at,
        text=text,
        summary=summary,
        topics=topics,
        document_type=classification.document_type,
        quality_score=classification.quality_score,
        links=links,
    )
