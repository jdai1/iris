from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfileInput:
    """Compressed source material for profile analysis."""

    source_id: int
    domain: str
    url: str
    fingerprint: str
    scraped_facts: dict
    documents: list[dict]
