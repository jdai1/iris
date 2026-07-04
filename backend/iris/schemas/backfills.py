from __future__ import annotations

from dataclasses import dataclass

from iris.schemas.ingestion import DocumentAnalysis


@dataclass(frozen=True)
class MetadataEmbeddingBackfillResult:
    """Summary counters for a metadata/embedding backfill run."""

    checked: int
    changed: int
    embedded: int
    failed: int
    dry_run: bool
    suspicious_only: bool


@dataclass(frozen=True)
class BackfillDocumentInput:
    """Detached document fields needed by one concurrent worker."""

    index: int
    total: int
    document_id: int
    url: str
    title: str | None
    document_type: str
    summary: str | None
    topics: list[str]
    category_slug: str | None
    extracted_text: str | None
    author: str | None
    has_published_date: bool
    link_count: int


@dataclass(frozen=True)
class BackfillDocumentOutput:
    """Result of one document metadata/embedding worker."""

    item: BackfillDocumentInput
    analysis: DocumentAnalysis | None
    embedding: list[float] | None
    changed: bool
    failed: bool
    error: str | None


@dataclass(frozen=True)
class SourceProfileBackfillResult:
    """Summary counters for a source profile analysis backfill."""

    checked: int
    succeeded: int
    failed: int
    force: bool


@dataclass(frozen=True)
class PgvectorBackfillResult:
    checked: int
    updated: int
    skipped: int
    dimensions: int
