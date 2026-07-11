from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from iris.schemas.enums import AgentStepKind, AgentToolName

if TYPE_CHECKING:
    from iris.models import Document


@dataclass(frozen=True)
class RankedDocument:
    document: Document
    score: float
    reason: str


@dataclass(frozen=True)
class AgentStep:
    kind: AgentStepKind
    title: str
    detail: str
    tool: AgentToolName | None = None
    query: str | None = None
    hits: int | None = None


@dataclass(frozen=True)
class AgentChatResult:
    answer: str
    results: list[RankedDocument]
    steps: list[AgentStep]


@dataclass(frozen=True)
class AgentToolRun:
    tool: AgentToolName
    query: str
    rows: list[RankedDocument]


@dataclass(frozen=True)
class AgentChatStreamEvent:
    event: str
    step: AgentStep | None = None
    rows: list[RankedDocument] = field(default_factory=list)
    result: AgentChatResult | None = None
    detail: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ProjectedEmbedding:
    """A document embedding projected into viewer space."""

    x: float
    y: float
    z: float
    cluster_id: int | None


@dataclass(frozen=True)
class EmbeddingProjection:
    """Projection output plus the method used to generate it."""

    points: list[ProjectedEmbedding]
    method: str


class AgentSearchOutput(BaseModel):
    answer: str = Field(
        description=(
            "One short natural-language search summary, at most two sentences. "
            "Do not list every result; the UI renders selected documents as the primary results. "
            "Never mention document IDs or database IDs."
        )
    )
    document_ids: list[int] = Field(
        default_factory=list,
        description="Internal document ids from tool results for the most relevant link cards. Never mention these ids in the answer. Leave empty when no documents are worth showing.",
    )
