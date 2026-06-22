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
    answer: str = Field(description="A concise conversational answer. Ask a clarifying question when the user has not given a searchable corpus request.")
    document_ids: list[int] = Field(
        default_factory=list,
        description="Only the most relevant document ids from tool results to show as link cards. Leave empty when no documents are worth showing.",
    )
