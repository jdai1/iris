from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iris.models import Document


@dataclass(frozen=True)
class RankedDocument:
    document: Document
    score: float
    reason: str


@dataclass(frozen=True)
class DigestRecommendation:
    document: Document
    score: float
    reason: str

    @property
    def document_id(self) -> int:
        return self.document.id
