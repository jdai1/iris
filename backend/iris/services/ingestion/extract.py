from __future__ import annotations

import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from iris.schemas.ingestion import ExtractedLink, ExtractedPage
from iris.services.ingestion.document_classifier import analyze_document, analyze_document_async


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


def extract_page(html: str, final_url: str) -> ExtractedPage:
    """Extract page text, metadata, links, and sync LLM document analysis."""
    parsed = _parse_html_page(html, final_url)
    analysis = analyze_document(
        url=final_url,
        metadata_title=parsed["title"],
        text=parsed["text"],
        link_count=parsed["content_link_count"],
        has_author=bool(parsed["author"]),
        has_published_date=bool(parsed["published_at"]),
    )
    return ExtractedPage(
        title=analysis.title,
        author=parsed["author"],
        published_at=parsed["published_at"],
        text=parsed["text"],
        summary=analysis.summary,
        topics=analysis.topics,
        document_type=analysis.document_type,
        category_slug=analysis.category_slug,
        links=parsed["links"],
    )


async def extract_page_async(html: str, final_url: str) -> ExtractedPage:
    """Extract page text, metadata, links, and async LLM document analysis."""
    parsed = _parse_html_page(html, final_url)
    analysis = await analyze_document_async(
        url=final_url,
        metadata_title=parsed["title"],
        text=parsed["text"],
        link_count=parsed["content_link_count"],
        has_author=bool(parsed["author"]),
        has_published_date=bool(parsed["published_at"]),
    )
    return ExtractedPage(
        title=analysis.title,
        author=parsed["author"],
        published_at=parsed["published_at"],
        text=parsed["text"],
        summary=analysis.summary,
        topics=analysis.topics,
        document_type=analysis.document_type,
        category_slug=analysis.category_slug,
        links=parsed["links"],
    )


def _parse_html_page(html: str, final_url: str) -> dict:
    """Parse HTML into extracted metadata before document analysis."""
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
    return {
        "title": title,
        "author": author,
        "published_at": published_at,
        "text": text,
        "content_link_count": content_link_count,
        "links": links,
    }
