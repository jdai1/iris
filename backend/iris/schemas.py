from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SourceCreate(BaseModel):
    url: str
    crawl_now: bool = False
    max_pages: int = 80
    max_depth: int = 3


class SourceOut(BaseModel):
    id: int
    canonical_domain: str
    homepage_url: str
    name: Optional[str]
    source_type: str
    status: str
    rss_url: Optional[str]
    first_seen_at: datetime
    last_checked_at: Optional[datetime]


class DocumentOut(BaseModel):
    id: int
    source_id: int
    source_domain: str
    url: str
    final_url: str
    document_type: str
    title: Optional[str]
    author: Optional[str]
    published_at: Optional[datetime]
    summary: Optional[str]
    topics: list[str]
    quality_score: Optional[float]


class SearchResultOut(BaseModel):
    document: DocumentOut
    score: float
    reason: str


class SearchOut(BaseModel):
    search_id: Optional[int]
    query: str
    answer: str
    results: list[SearchResultOut]


class DigestItemOut(BaseModel):
    id: int
    document: DocumentOut
    score: float
    reason: str
    status: str


class FeedbackIn(BaseModel):
    document_id: int
    surface: str = Field(pattern="^(search|digest|source_queue|document)$")
    action: str = Field(pattern="^(save|dismiss|skip|open|read|like)$")
    search_id: Optional[int] = None
    digest_item_id: Optional[int] = None


class CrawlOut(BaseModel):
    id: int
    source_id: int
    status: str
    pages_queued: int
    pages_fetched: int
    pages_failed: int
    documents_indexed: int
    links_seen: int
    sources_discovered: int
    error: Optional[str]


class GraphOut(BaseModel):
    nodes: list[dict]
    edges: list[dict]
