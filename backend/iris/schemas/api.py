from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from iris.models import FeedbackAction, FeedbackSurface


class SourceCreateSchema(BaseModel):
    url: str
    crawl_now: bool = False
    max_pages: int = 80
    max_depth: int = 3


class SourceSchema(BaseModel):
    id: int
    canonical_domain: str
    url: str
    name: str | None
    status: str
    rss_url: str | None
    first_seen_at: datetime
    last_checked_at: datetime | None


class DocumentSchema(BaseModel):
    id: int
    source_id: int
    source_domain: str
    url: str
    document_type: str
    title: str | None
    author: str | None
    published_at: datetime | None
    summary: str | None
    topics: list[str]


class SearchResultSchema(BaseModel):
    document: DocumentSchema
    score: float
    reason: str


class SearchSchema(BaseModel):
    search_id: int | None
    query: str
    answer: str
    results: list[SearchResultSchema]


class DigestItemSchema(BaseModel):
    id: int
    document: DocumentSchema
    score: float
    reason: str
    status: str


class FeedbackSchema(BaseModel):
    document_id: int
    surface: str = Field(pattern=f"^({'|'.join(sorted(FeedbackSurface.values()))})$")
    action: str = Field(pattern=f"^({'|'.join(sorted(FeedbackAction.values()))})$")
    search_id: int | None = None
    digest_item_id: int | None = None


class CrawlSchema(BaseModel):
    id: int
    source_id: int
    status: str
    pages_queued: int
    pages_fetched: int
    pages_failed: int
    documents_indexed: int
    links_seen: int
    sources_discovered: int
    error: str | None


class GraphSchema(BaseModel):
    nodes: list[dict]
    edges: list[dict]
