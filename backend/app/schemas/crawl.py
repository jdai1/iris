from datetime import date
import uuid

from pydantic import BaseModel

from app.enums.core import DomainStatus


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


class DomainMappingCreateParams(BaseModel):
    """Parameters for creating a domain mapping."""

    source_domain_id: uuid.UUID
    target_domain_id: uuid.UUID


class DomainCreateParams(BaseModel):
    """Parameters for creating a domain."""

    domain_url: str
    entity: str | None = None
    name: str | None = None
    status: DomainStatus = DomainStatus.PENDING
    error_message: str | None = None


class LinkCreateParams(BaseModel):
    """Parameters for creating a link."""

    url: str
    domain_id: uuid.UUID


class EntryCreateParams(BaseModel):
    """Parameters for creating an entry."""

    link_id: uuid.UUID
    title: str
    summary: str
    topics: list[str]
    author: str
    date_published: date | None = None
