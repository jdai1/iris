from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeedCategory:
    """Definition for one default system category."""

    slug: str
    name: str
    description: str
    color: str
