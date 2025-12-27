from datetime import date
import uuid

from pydantic import BaseModel


class PageLinks(BaseModel):
    """Links extracted from a crawled page."""

    internal: list[str]
    external: list[str]


class PageCrawlResult(BaseModel):
    """Result of crawling a single web page."""

    url: str
    redirected_url: str
    cleaned_html: str
    links: PageLinks


class EntryModel(BaseModel):
    """Pydantic representation of an Entry."""

    id: uuid.UUID
    link_id: uuid.UUID
    title: str
    summary: str
    topics: list[str]
    author: str
    date_published: date | None


class DomainCrawlResult(BaseModel):
    """Result of crawling an entire domain."""

    entries: list[EntryModel]
    external_domains: list[str]
    external_links: list[str]
    target_internal_links: list[str]
    nontarget_internal_links: list[str]


class LinkMappingCreateParams(BaseModel):
    """Parameters for creating a link mapping."""

    source_link_id: uuid.UUID
    target_link_id: uuid.UUID
