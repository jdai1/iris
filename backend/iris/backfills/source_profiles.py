"""Backfill persisted source profile analyses."""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from iris.dao import db
from iris.dao import source_profiles as profile_dao
from iris.services.retrieval.source_profiles import generate_source_profile


def log(message: str) -> None:
    """Print progress immediately for long-running terminal backfills."""
    print(message, flush=True)


@dataclass(frozen=True)
class SourceProfileBackfillResult:
    """Summary counters for a source profile analysis backfill."""

    checked: int
    succeeded: int
    missing_key: int
    failed: int
    force: bool


def backfill_source_profiles(*, limit: int | None = None, force: bool = False) -> SourceProfileBackfillResult:
    """Generate cached profile analyses for indexed sources with fetched documents."""
    sources = profile_dao.get_sources_for_profile_backfill(limit=limit)
    succeeded = 0
    missing_key = 0
    failed = 0
    log(f"source profile backfill selected={len(sources)} force={force}")
    for idx, source in enumerate(sources, start=1):
        analysis = generate_source_profile(source, force=force)
        if analysis.status == "succeeded":
            succeeded += 1
        elif analysis.status == "missing_key":
            missing_key += 1
        else:
            failed += 1
        log(
            f"{idx}/{len(sources)} source={source.canonical_domain} status={analysis.status} "
            f"display_name={analysis.display_name or 'none'} evidence={len(analysis.evidence_document_ids or [])}"
        )
        if analysis.error:
            log(f"  error={analysis.error[:300]}")
        if idx % 10 == 0:
            db.flush()
            log(f"progress checked={idx}/{len(sources)} succeeded={succeeded} missing_key={missing_key} failed={failed}")
    db.flush()
    return SourceProfileBackfillResult(
        checked=len(sources),
        succeeded=succeeded,
        missing_key=missing_key,
        failed=failed,
        force=force,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m iris.backfills.source_profiles")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    with db.session_scope():
        result = backfill_source_profiles(limit=args.limit or None, force=args.force)
        log(
            f"checked={result.checked} succeeded={result.succeeded} missing_key={result.missing_key} "
            f"failed={result.failed} force={result.force}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
