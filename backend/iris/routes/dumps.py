from __future__ import annotations

from iris.dao.bookshelf import effective_status
from iris.models import BookshelfCollection, CrawlJob, Document, Source, SourceProfileAnalysis, UserDocumentMapping
from iris.schemas.api import BookshelfCollectionSchema, BookshelfEntrySchema, CrawlSchema, DocumentSchema, SourceProfileAnalysisSchema, SourceSchema


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
        uuid=document.uuid,
        source_id=document.source_id,
        source_domain=document.source.canonical_domain,
        url=document.url,
        document_type=document.document_type,
        category=document.category,
        title=document.title,
        author=document.author,
        published_at=document.published_at,
        summary=document.summary,
        one_liner=document.one_liner,
        audience=document.audience,
        takeaways=document.takeaways or [],
        topics=document.topics or [],
    )


def dump_source_profile_analysis(analysis: SourceProfileAnalysis) -> SourceProfileAnalysisSchema:
    return SourceProfileAnalysisSchema(
        id=analysis.id,
        source_id=analysis.source_id,
        source_domain=analysis.source.canonical_domain,
        status=analysis.status,
        display_name=analysis.display_name,
        generated_at=analysis.generated_at,
        model=analysis.model,
        input_fingerprint=analysis.input_fingerprint,
        bio=analysis.bio,
        themes=analysis.themes,
        writing_style=analysis.writing_style,
        strong_takes=analysis.strong_takes,
        public_links=analysis.public_links,
        public_contact=analysis.public_contact,
        caveats=analysis.caveats,
        scraped_facts=analysis.scraped_facts,
        error=analysis.error,
    )


def dump_bookshelf_entry(mapping: UserDocumentMapping, tags: list[str] | None = None) -> BookshelfEntrySchema:
    return BookshelfEntrySchema(
        document=dump_document(mapping.document),
        status=effective_status(mapping),
        favorited=mapping.favorited_at is not None,
        note=mapping.note,
        intent_note=mapping.intent_note,
        tags=tags or [],
        first_seen_at=mapping.first_seen_at,
        read_at=mapping.read_at,
        archived_at=mapping.dismissed_at,
        favorited_at=mapping.favorited_at,
    )


def dump_bookshelf_collection(collection: BookshelfCollection, entries: list[BookshelfEntrySchema]) -> BookshelfCollectionSchema:
    return BookshelfCollectionSchema(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        visibility=collection.visibility,
        share_token=collection.share_token,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
        items=entries,
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
