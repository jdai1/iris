from __future__ import annotations

from iris.models import CrawlJob, Document, Source, SourceProfileAnalysis
from iris.schemas.api import CrawlSchema, DigestRecommendationSchema, DocumentSchema, SourceProfileAnalysisSchema, SourceSchema
from iris.schemas.retrieval import DigestRecommendation


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
        category=document.category,
        title=document.title,
        author=document.author,
        published_at=document.published_at,
        summary=document.summary,
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


def dump_digest_recommendation(item: DigestRecommendation) -> DigestRecommendationSchema:
    return DigestRecommendationSchema(
        document=dump_document(item.document),
        score=item.score,
        reason=item.reason,
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
