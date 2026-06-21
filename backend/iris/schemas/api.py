from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from iris.schemas.enums import AgentMessageRole, AgentStepKind, SourceProfileAnalysisStatus, SourceProfileLinkKind

T = TypeVar("T")


class PageSchema(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    has_next: bool
    has_previous: bool


class HealthSchema(BaseModel):
    ok: bool
    sources: int
    documents: int


class HealthCountsSchema(BaseModel):
    sources: int
    documents: int


class UserSchema(BaseModel):
    id: int
    slug: str
    firebase_uid: str | None = None
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None


class SourceCreateSchema(BaseModel):
    url: str
    crawl_now: bool = False
    max_pages: int = 80
    max_depth: int = 3
    active_pages: int = 4


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
    category: str
    title: str | None
    author: str | None
    published_at: datetime | None
    summary: str | None
    topics: list[str]


class DocumentOutgoingLinkSchema(BaseModel):
    target_url: str
    target_domain: str | None
    target_document_id: int | None
    anchor_text: str | None
    context: str | None


class DocumentIncomingLinkSchema(BaseModel):
    source_document_id: int
    target_url: str
    anchor_text: str | None


class DocumentDetailSchema(DocumentSchema):
    extracted_text: str | None
    outgoing_links: list[DocumentOutgoingLinkSchema]
    incoming_links: list[DocumentIncomingLinkSchema]


class SearchResultSchema(BaseModel):
    document: DocumentSchema
    score: float
    reason: str


class AgentChatRequestSchema(BaseModel):
    message: str
    limit: int | None = None
    conversation_id: int | None = None


class AgentStepSchema(BaseModel):
    kind: AgentStepKind
    title: str
    detail: str
    tool: str | None = None
    query: str | None = None
    hits: int | None = None


class SearchSchema(BaseModel):
    query: str
    answer: str
    results: list[SearchResultSchema]


class AgentChatSchema(BaseModel):
    conversation_id: int
    user_message_id: int
    assistant_message_id: int
    message: str
    answer: str
    results: list[SearchResultSchema]
    steps: list[AgentStepSchema]


class AgentConversationSummarySchema(BaseModel):
    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime
    message_count: int


class AgentMessageSchema(BaseModel):
    id: int
    role: AgentMessageRole
    content: str
    created_at: datetime
    steps: list[AgentStepSchema] = []
    results: list[SearchResultSchema] = []


class AgentConversationSchema(BaseModel):
    id: int
    title: str | None
    created_at: datetime
    updated_at: datetime
    messages: list[AgentMessageSchema]


class DigestRecommendationSchema(BaseModel):
    document: DocumentSchema
    score: float
    reason: str


class EmbeddingMapPointSchema(BaseModel):
    document: DocumentSchema
    x: float
    y: float
    z: float
    cluster_id: int | None


class EmbeddingMapSchema(BaseModel):
    points: list[EmbeddingMapPointSchema]
    total_embedded: int
    dimensions: int
    projection_method: str


class EmbeddingNeighborSchema(BaseModel):
    document: DocumentSchema
    similarity: float


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


class AdminOverviewSchema(BaseModel):
    totals: dict[str, int]
    source_statuses: dict[str, int]
    document_types: dict[str, int]


class AdminLatestJobSchema(BaseModel):
    id: int
    index_run_id: int | None
    status: str
    pages_fetched: int
    pages_failed: int
    documents_indexed: int
    links_seen: int
    sources_discovered: int
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    outcome: str


class AdminSourceSchema(BaseModel):
    id: int
    canonical_domain: str
    url: str
    status: str
    description: str | None
    rss_url: str | None
    sitemap_url: str | None
    first_seen_at: datetime
    last_checked_at: datetime | None
    document_count: int
    essay_count: int
    latest_job: AdminLatestJobSchema | None


class SourceProfileLinkSchema(BaseModel):
    label: str
    url: str
    kind: SourceProfileLinkKind


class SourceProfileTakeSchema(BaseModel):
    take: str


class SourceProfileTopicSchema(BaseModel):
    topic: str
    count: int


class SourceProfilePageSchema(BaseModel):
    id: int
    title: str | None
    url: str
    summary: str | None


class SourceProfileFactsSchema(BaseModel):
    domain: str | None = None
    homepage: str | None = None
    rss_url: str | None = None
    sitemap_url: str | None = None
    author_candidates: list[str] = Field(default_factory=list)
    top_topics: list[SourceProfileTopicSchema] = Field(default_factory=list)
    profile_pages: list[SourceProfilePageSchema] = Field(default_factory=list)
    public_links: list[SourceProfileLinkSchema] = Field(default_factory=list)
    public_contact: list[SourceProfileLinkSchema] = Field(default_factory=list)
    document_counts: dict[str, int] = Field(default_factory=dict)


class SourceProfileAnalysisSchema(BaseModel):
    id: int
    source_id: int
    source_domain: str
    status: SourceProfileAnalysisStatus
    display_name: str | None
    generated_at: datetime | None
    model: str | None
    input_fingerprint: str | None
    bio: str | None
    themes: list[str] | None
    writing_style: list[str] | None
    strong_takes: list[SourceProfileTakeSchema] | None
    public_links: list[SourceProfileLinkSchema] | None
    public_contact: list[SourceProfileLinkSchema] | None
    caveats: list[str] | None
    scraped_facts: SourceProfileFactsSchema | None
    error: str | None


class AdminCrawlJobSchema(BaseModel):
    id: int
    source_id: int
    source_domain: str
    index_run_id: int | None
    status: str
    pages_fetched: int
    pages_failed: int
    documents_indexed: int
    current_document_count: int
    links_seen: int
    sources_discovered: int
    started_at: datetime
    finished_at: datetime | None
    error: str | None
    outcome: str


class AdminIndexRunSchema(BaseModel):
    id: int
    status: str
    mode: str
    dry_run: bool
    started_at: datetime
    finished_at: datetime | None
    budget_sources: int
    max_pages: int
    max_depth: int
    planned_sources: int
    attempted_sources: int
    crawled_sources: int
    ignored_sources: int
    documents_indexed: int
    current_document_count: int
    links_seen: int
    sources_discovered: int
    errors: int
    stop_reason: str | None


class GraphNodeSchema(BaseModel):
    id: str
    label: str
    type: str
    domain: str
    url: str | None = None
    subtitle: str | None = None
    summary: str | None = None
    size: float = 1.0


class GraphEdgeSchema(BaseModel):
    source: str
    target: str
    label: str | None
    weight: float = 1.0


class GraphSchema(BaseModel):
    nodes: list[GraphNodeSchema]
    edges: list[GraphEdgeSchema]
