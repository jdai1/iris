from __future__ import annotations

from iris.models import CrawlJob, DigestItem, Document, Source
from iris.schemas.api import CrawlSchema, DigestItemSchema, DocumentSchema, SourceSchema


def dump_source(source: Source) -> SourceSchema:
    return SourceSchema(
        id=source.id,
        canonical_domain=source.canonical_domain,
        url=source.url,
        name=source.name,
        status=source.status,
        rss_url=source.rss_url,
        first_seen_at=source.first_seen_at,
        last_checked_at=source.last_checked_at,
    )


def dump_document(document: Document) -> DocumentSchema:
    return DocumentSchema(
        id=document.id,
        source_id=document.source_id,
        source_domain=document.source.canonical_domain,
        url=document.url,
        document_type=document.document_type,
        title=document.title,
        author=document.author,
        published_at=document.published_at,
        summary=document.summary,
        topics=document.topics or [],
    )


def dump_digest_item(item: DigestItem) -> DigestItemSchema:
    return DigestItemSchema(
        id=item.id,
        document=dump_document(item.document),  # type: ignore[attr-defined]
        score=item.score,
        reason=item.reason,
        status=item.status,
    )


def dump_crawl_job(job: CrawlJob) -> CrawlSchema:
    return CrawlSchema(
        id=job.id,
        source_id=job.source_id,
        status=job.status,
        pages_queued=job.pages_queued,
        pages_fetched=job.pages_fetched,
        pages_failed=job.pages_failed,
        documents_indexed=job.documents_indexed,
        links_seen=job.links_seen,
        sources_discovered=job.sources_discovered,
        error=job.error,
    )
