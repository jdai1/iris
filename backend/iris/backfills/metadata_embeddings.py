"""Backfill LLM document metadata and topic-weighted embeddings."""

from __future__ import annotations

import argparse
import asyncio

from iris.dao import db
from iris.dao.categories import assign_category, get_or_create_category
from iris.dao import documents as documents_dao
from iris.dao import maintenance as maintenance_dao
from iris.dao import reporting as reporting_dao
from iris.schemas.backfills import BackfillDocumentInput, BackfillDocumentOutput, MetadataEmbeddingBackfillResult
from iris.services.ingestion.document_classifier import analyze_document_async
from iris.services.ingestion.embedding import document_embedding_text, embed_text_async


def log(message: str) -> None:
    """Print progress immediately for long-running terminal backfills."""
    print(message, flush=True)


def backfill_metadata_and_embeddings(
    *,
    source_domain: str | None = None,
    limit: int | None = 50,
    suspicious_only: bool = True,
    dry_run: bool = False,
    embed: bool = True,
    openai_embeddings: bool | None = True,
    max_attempts: int = 2,
    active_documents: int = 4,
) -> MetadataEmbeddingBackfillResult:
    """Refresh LLM metadata and re-embed documents with bounded concurrency."""
    documents = maintenance_dao.get_documents_for_metadata_backfill(
        source_domain=source_domain,
        limit=limit,
        suspicious_only=suspicious_only,
    )
    items = [
        BackfillDocumentInput(
            index=idx,
            total=len(documents),
            document_id=document.id,
            url=document.url,
            title=document.title,
            document_type=str(document.document_type),
            summary=document.summary,
            one_liner=document.one_liner,
            audience=document.audience,
            takeaways=list(document.takeaways or []),
            topics=list(document.topics or []),
            category_slug=None,
            extracted_text=document.extracted_text,
            author=document.author,
            has_published_date=bool(document.published_at),
            link_count=reporting_dao.count_document_links(document.id),
        )
        for idx, document in enumerate(documents, start=1)
    ]
    log(
        f"backfill selected={len(items)} active_documents={max(1, active_documents)} "
        f"dry_run={dry_run} embed={embed and not dry_run} suspicious_only={suspicious_only}"
    )
    outputs = asyncio.run(
        _run_document_workers(
            items,
            dry_run=dry_run,
            embed=embed,
            openai_embeddings=openai_embeddings,
            max_attempts=max_attempts,
            active_documents=active_documents,
        )
    )

    changed = 0
    embedded = 0
    failed = 0
    documents_by_id = {document.id: document for document in documents}
    for processed, output in enumerate(outputs, start=1):
        item = output.item
        if output.failed or output.analysis is None:
            failed += 1
            log(f"{item.index}/{item.total} doc={item.document_id} failed: {output.error}")
            continue
        analysis = output.analysis
        log(
            f"{item.index}/{item.total} doc={item.document_id} "
            f"type {item.document_type}->{analysis.document_type} "
            f"category={analysis.category_slug or 'none'} "
            f"title {item.title or item.url!r}->{analysis.title!r}"
        )
        if dry_run:
            continue
        document = documents_by_id[item.document_id]
        if output.changed:
            changed += 1
            documents_dao.update_document_analysis(document, analysis)
        if analysis.category_slug:
            assign_category(document, get_or_create_category(analysis.category_slug), assigned_by="llm")
        if output.embedding is not None:
            documents_dao.update_document_embedding(document, output.embedding)
            embedded += 1
        if processed % 10 == 0:
            db.flush()
            log(f"progress checked={processed}/{len(documents)} changed={changed} embedded={embedded} failed={failed}")
    db.flush()
    return MetadataEmbeddingBackfillResult(
        checked=len(documents),
        changed=changed,
        embedded=embedded,
        failed=failed,
        dry_run=dry_run,
        suspicious_only=suspicious_only,
    )


async def _run_document_workers(
    items: list[BackfillDocumentInput],
    *,
    dry_run: bool,
    embed: bool,
    openai_embeddings: bool | None,
    max_attempts: int,
    active_documents: int,
) -> list[BackfillDocumentOutput]:
    """Run document workers under the active-documents semaphore."""
    semaphore = asyncio.Semaphore(max(1, active_documents))
    tasks = [
        asyncio.create_task(
            _process_document(
                item,
                semaphore=semaphore,
                dry_run=dry_run,
                embed=embed,
                openai_embeddings=openai_embeddings,
                max_attempts=max_attempts,
            )
        )
        for item in items
    ]
    outputs: list[BackfillDocumentOutput] = []
    completed = 0
    for task in asyncio.as_completed(tasks):
        outputs.append(await task)
        completed += 1
        if completed % 10 == 0 or completed == len(tasks):
            log(f"worker progress completed={completed}/{len(tasks)} active_documents={max(1, active_documents)}")
    return outputs


async def _process_document(
    item: BackfillDocumentInput,
    *,
    semaphore: asyncio.Semaphore,
    dry_run: bool,
    embed: bool,
    openai_embeddings: bool | None,
    max_attempts: int,
) -> BackfillDocumentOutput:
    """Analyze and optionally embed one document inside the concurrency limit."""
    async with semaphore:
        log(f"start {item.index}/{item.total} doc={item.document_id} title={item.title or item.url!r}")
        analysis = None
        last_error: Exception | None = None
        for attempt in range(1, max(1, max_attempts) + 1):
            try:
                analysis = await analyze_document_async(
                    url=item.url,
                    metadata_title=item.title,
                    text=item.extracted_text or "",
                    link_count=item.link_count,
                    has_author=bool(item.author),
                    has_published_date=item.has_published_date,
                )
                break
            except Exception as exc:
                last_error = exc
                log(f"{item.index}/{item.total} doc={item.document_id} attempt={attempt} failed: {exc}")
        if analysis is None:
            return BackfillDocumentOutput(
                item=item,
                analysis=None,
                embedding=None,
                changed=False,
                failed=True,
                error=str(last_error or "document analysis failed"),
            )
        changed = (
            item.document_type != analysis.document_type
            or item.title != analysis.title
            or (item.summary or "") != analysis.summary
            or (item.one_liner or "") != (analysis.one_liner or "")
            or (item.audience or "") != (analysis.audience or "")
            or item.takeaways != (analysis.takeaways or [])
            or item.topics != analysis.topics
            or item.category_slug != analysis.category_slug
        )
        embedding = None
        if embed and not dry_run:
            text = document_embedding_text(
                title=analysis.title,
                summary=analysis.summary,
                topics=analysis.topics,
                extracted_text=item.extracted_text,
            )
            embedding = await embed_text_async(text, prefer_openai=openai_embeddings)
        log(
            f"done {item.index}/{item.total} doc={item.document_id} "
            f"type {item.document_type}->{analysis.document_type} "
            f"category={analysis.category_slug or 'none'} changed={changed}"
        )
        return BackfillDocumentOutput(
            item=item,
            analysis=analysis,
            embedding=embedding,
            changed=changed,
            failed=False,
            error=None,
        )


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m iris.backfills.metadata_embeddings")
    parser.add_argument("--source")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    parser.add_argument("--local-embeddings", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--active-documents", type=int, default=4)
    args = parser.parse_args()

    with db.session_scope():
        result = backfill_metadata_and_embeddings(
            source_domain=args.source,
            limit=args.limit,
            suspicious_only=not args.all,
            dry_run=args.dry_run,
            embed=not args.skip_embeddings,
            openai_embeddings=False if args.local_embeddings else True,
            max_attempts=args.max_attempts,
            active_documents=args.active_documents,
        )
        log(
            f"checked={result.checked} changed={result.changed} embedded={result.embedded} "
            f"failed={result.failed} suspicious_only={result.suspicious_only} dry_run={result.dry_run}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
