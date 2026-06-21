"""Backfill persisted source profile analyses."""

from __future__ import annotations

import argparse

from iris.dao import db
from iris.dao import source_profiles as profile_dao
from iris.schemas.backfills import SourceProfileBackfillResult
from iris.schemas.enums import SourceProfileAnalysisStatus
from iris.services.retrieval.source_profiles import generate_source_profile


def log(message: str) -> None:
    """Print progress immediately for long-running terminal backfills."""
    print(message, flush=True)


def backfill_source_profiles(*, limit: int | None = None, force: bool = False) -> SourceProfileBackfillResult:
    """Generate cached profile analyses for indexed sources with fetched documents."""
    sources = profile_dao.get_sources_for_profile_backfill(limit=limit)
    succeeded = 0
    failed = 0
    log(f"source profile backfill selected={len(sources)} force={force}")
    for idx, source in enumerate(sources, start=1):
        analysis = generate_source_profile(source, force=force)
        if analysis.status == SourceProfileAnalysisStatus.SUCCEEDED:
            succeeded += 1
        else:
            failed += 1
        log(
            f"{idx}/{len(sources)} source={source.canonical_domain} status={analysis.status} "
            f"display_name={analysis.display_name or 'none'}"
        )
        if analysis.error:
            log(f"  error={analysis.error[:300]}")
        if idx % 10 == 0:
            db.flush()
            log(f"progress checked={idx}/{len(sources)} succeeded={succeeded} failed={failed}")
    db.flush()
    return SourceProfileBackfillResult(
        checked=len(sources),
        succeeded=succeeded,
        failed=failed,
        force=force,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m iris.backfills.source_profiles")
    parser.add_argument("--domain")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    with db.session_scope():
        if args.domain:
            source = profile_dao.get_source_by_domain(args.domain)
            if not source:
                log(f"source not found: {args.domain}")
                return 1
            analysis = generate_source_profile(source, force=args.force)
            log(
                f"profile source={source.canonical_domain} status={analysis.status} "
                f"display_name={analysis.display_name or 'none'}"
            )
            if analysis.error:
                log(f"error={analysis.error}")
            return 0
        result = backfill_source_profiles(limit=args.limit or None, force=args.force)
        log(
            f"checked={result.checked} succeeded={result.succeeded} failed={result.failed} force={result.force}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
