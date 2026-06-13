from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


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
    category_slug: str | None
    links: list[ExtractedLink]


@dataclass(frozen=True)
class DocumentClassification:
    document_type: str
    reason: str


@dataclass(frozen=True)
class DocumentAnalysis:
    title: str | None
    summary: str
    topics: list[str]
    document_type: str
    category_slug: str | None


@dataclass(frozen=True)
class SourceClassification:
    status: str
    reason: str


@dataclass(frozen=True)
class SourceClassifierResult:
    should_crawl: bool
    reason: str


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    content_type: str
    text: str
