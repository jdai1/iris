from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.models import Source


@dataclass(frozen=True)
class SourcePriority:
    source: Source
    score: float
    inbound_links: int
    referring_sources: int
    bfs_links: int
    bfs_seed_source_id: int | None
    bfs_seed_domain: str | None
    reason: str


@dataclass(frozen=True)
class SourcePriorityPayload:
    source_id: int
    domain: str
    status: str
    score: float
    inbound_links: int
    referring_sources: int
    bfs_links: int
    bfs_seed_source_id: int | None
    bfs_seed_domain: str | None
    reason: str


@dataclass(frozen=True)
class PlannedSourceEvent:
    source_id: int
    domain: str
    score: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class SourceFinishedEventPayload:
    max_documents_per_source: int | None = None
