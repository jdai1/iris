from pydantic import BaseModel

from app.enums.core import EntityType


class EntryParseResult(BaseModel):
    """Result of parsing an entry from HTML."""

    should_pursue: bool
    title: str
    summary: str
    topics: list[str]
    author: str
    date_published: str


class EntryWithEmbedding(EntryParseResult):
    """Entry parse result with its embedding vector."""

    embedding: list[float]


class DomainClassificationResult(BaseModel):
    """Result of classifying a domain."""

    url: str
    entity: EntityType
    name: str
    blog: bool
