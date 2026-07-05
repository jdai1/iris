"""Backfill document summaries without changing other analysis fields."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from iris.dao import db
from iris.dao import maintenance as maintenance_dao
from iris.dao import reporting as reporting_dao
from iris.models import Document
from iris.services.ingestion.document_classifier import analyze_document_async


@dataclass(frozen=True)
class SummaryBackfillItem:
    index: int
    total: int
    document_id: int
    url: str
    title: str | None
    summary: str | None
    one_liner: str | None
    audience: str | None
    takeaways: list[str]
    extracted_text: str | None
    author: str | None
    has_published_date: bool
    link_count: int


@dataclass(frozen=True)
class SummaryBackfillOutput:
    item: SummaryBackfillItem
    summary: str | None
    one_liner: str | None
    audience: str | None
    takeaways: list[str] | None
    changed: bool
    failed: bool
    error: str | None


@dataclass(frozen=True)
class SummaryBackfillResult:
    checked: int
    changed: int
    failed: int
    dry_run: bool


def log(message: str) -> None:
    """Print progress immediately for long-running terminal backfills."""
    print(message, flush=True)


def backfill_document_summaries(
    *,
    source_domain: str | None = None,
    limit: int | None = 0,
    dry_run: bool = False,
    max_attempts: int = 2,
    active_documents: int = 4,
) -> SummaryBackfillResult:
    """Regenerate summaries for fetched documents and persist only the summary field."""
    documents = maintenance_dao.get_fetched_documents(source_domain=source_domain, limit=limit)
    items = [
        SummaryBackfillItem(
            index=idx,
            total=len(documents),
            document_id=document.id,
            url=document.url,
            title=document.title,
            summary=document.summary,
            one_liner=document.one_liner,
            audience=document.audience,
            takeaways=list(document.takeaways or []),
            extracted_text=document.extracted_text,
            author=document.author,
            has_published_date=bool(document.published_at),
            link_count=reporting_dao.count_document_links(document.id),
        )
        for idx, document in enumerate(documents, start=1)
    ]
    log(
        f"summary backfill selected={len(items)} active_documents={max(1, active_documents)} "
        f"dry_run={dry_run}"
    )
    outputs = asyncio.run(
        _run_summary_workers(
            items,
            max_attempts=max_attempts,
            active_documents=active_documents,
        )
    )

    changed = 0
    failed = 0
    documents_by_id: dict[int, Document] = {document.id: document for document in documents}
    for processed, output in enumerate(outputs, start=1):
        item = output.item
        if output.failed or output.summary is None:
            failed += 1
            log(f"{item.index}/{item.total} doc={item.document_id} failed: {output.error}")
            continue
        if output.changed:
            changed += 1
            log(f"{item.index}/{item.total} doc={item.document_id} summary changed")
            if not dry_run:
                document = documents_by_id[item.document_id]
                document.summary = output.summary
                document.one_liner = output.one_liner
                document.audience = output.audience
                document.takeaways = output.takeaways or []
        else:
            log(f"{item.index}/{item.total} doc={item.document_id} summary unchanged")
        if not dry_run and processed % 10 == 0:
            db.flush()
            log(f"progress checked={processed}/{len(documents)} changed={changed} failed={failed}")
    if not dry_run:
        db.flush()
    return SummaryBackfillResult(checked=len(documents), changed=changed, failed=failed, dry_run=dry_run)


async def _run_summary_workers(
    items: list[SummaryBackfillItem],
    *,
    max_attempts: int,
    active_documents: int,
) -> list[SummaryBackfillOutput]:
    """Run summary workers under the active-documents semaphore."""
    semaphore = asyncio.Semaphore(max(1, active_documents))
    tasks = [
        asyncio.create_task(
            _process_summary(
                item,
                semaphore=semaphore,
                max_attempts=max_attempts,
            )
        )
        for item in items
    ]
    outputs: list[SummaryBackfillOutput] = []
    completed = 0
    for task in asyncio.as_completed(tasks):
        outputs.append(await task)
        completed += 1
        if completed % 10 == 0 or completed == len(tasks):
            log(f"worker progress completed={completed}/{len(tasks)} active_documents={max(1, active_documents)}")
    return outputs


async def _process_summary(
    item: SummaryBackfillItem,
    *,
    semaphore: asyncio.Semaphore,
    max_attempts: int,
) -> SummaryBackfillOutput:
    """Regenerate the summary for one document."""
    async with semaphore:
        log(f"start {item.index}/{item.total} doc={item.document_id} title={item.title or item.url!r}")
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
                summary = analysis.summary
                one_liner = analysis.one_liner
                audience = analysis.audience
                takeaways = analysis.takeaways or []
                return SummaryBackfillOutput(
                    item=item,
                    summary=summary,
                    one_liner=one_liner,
                    audience=audience,
                    takeaways=takeaways,
                    changed=(
                        (item.summary or "") != summary
                        or (item.one_liner or "") != (one_liner or "")
                        or (item.audience or "") != (audience or "")
                        or item.takeaways != takeaways
                    ),
                    failed=False,
                    error=None,
                )
            except Exception as exc:
                last_error = exc
                log(f"{item.index}/{item.total} doc={item.document_id} attempt={attempt} failed: {exc}")
        return SummaryBackfillOutput(
            item=item,
            summary=None,
            one_liner=None,
            audience=None,
            takeaways=None,
            changed=False,
            failed=True,
            error=str(last_error or "summary analysis failed"),
        )


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m iris.backfills.document_summaries")
    parser.add_argument("--source")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--active-documents", type=int, default=4)
    args = parser.parse_args()

    with db.session_scope():
        result = backfill_document_summaries(
            source_domain=args.source,
            limit=args.limit,
            dry_run=args.dry_run,
            max_attempts=args.max_attempts,
            active_documents=args.active_documents,
        )
        log(f"checked={result.checked} changed={result.changed} failed={result.failed} dry_run={result.dry_run}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
