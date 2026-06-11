from __future__ import annotations

from iris.models import CrawlJob, DigestItem, Document, Source
from iris.schemas import CrawlOut, DigestItemOut, DocumentOut, SourceOut


def source_out(source: Source) -> SourceOut:
    return SourceOut(
        id=source.id,
        canonical_domain=source.canonical_domain,
        homepage_url=source.homepage_url,
        name=source.name,
        source_type=source.source_type,
        status=source.status,
        rss_url=source.rss_url,
        first_seen_at=source.first_seen_at,
        last_checked_at=source.last_checked_at,
    )


def document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        source_id=document.source_id,
        source_domain=document.source.canonical_domain,
        url=document.url,
        final_url=document.final_url,
        document_type=document.document_type,
        title=document.title,
        author=document.author,
        published_at=document.published_at,
        summary=document.summary,
        topics=[topic for topic in (document.topics or "").split(",") if topic],
        quality_score=document.quality_score,
    )


def digest_item_out(item: DigestItem) -> DigestItemOut:
    return DigestItemOut(
        id=item.id,
        document=document_out(item.document),  # type: ignore[attr-defined]
        score=item.score,
        reason=item.reason,
        status=item.status,
    )


def crawl_out(job: CrawlJob) -> CrawlOut:
    return CrawlOut(
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
