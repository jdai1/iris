from __future__ import annotations

from enum import Enum


class StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

    @classmethod
    def values(cls) -> set[str]:
        return {item.value for item in cls}


class SourceStatus(StringEnum):
    QUEUED = "queued"
    INDEXED = "indexed"
    IGNORED = "ignored"
    CRAWLING = "crawling"
    FAILED = "failed"


class DocumentType(StringEnum):
    UNKNOWN = "unknown"
    ESSAY = "essay"
    COLLECTION = "collection"
    PROFILE = "profile"
    REFERENCE = "reference"
    IGNORE = "ignore"


class DocumentCategory(StringEnum):
    UNKNOWN = "unknown"
    SCIENCE = "science"
    TECHNOLOGY = "technology"
    SOFTWARE = "software"
    STARTUPS = "startups"
    PHILOSOPHY = "philosophy"
    HISTORY = "history"
    POLITICS = "politics"
    ECONOMICS = "economics"
    HEALTH = "health"
    CULTURE = "culture"
    PERSONAL = "personal"
    OTHER = "other"


class CrawlStatus(StringEnum):
    PENDING = "pending"
    FETCHED = "fetched"


class LinkType(StringEnum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class CrawlJobStatus(StringEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    STOPPED = "stopped"


class IndexRunStatus(StringEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STOPPED = "stopped"


class IndexMode(StringEnum):
    AUTOPILOT = "autopilot"


class IndexEventType(StringEnum):
    PLAN_CREATED = "plan_created"
    SOURCE_HOMEPAGE_NORMALIZED = "source_homepage_normalized"
    SOURCE_STARTED = "source_started"
    SOURCE_FINISHED = "source_finished"


class TagScope(StringEnum):
    SYSTEM = "system"
    USER = "user"


class BookshelfStatus(StringEnum):
    SAVED = "saved"
    READ = "read"
    ARCHIVED = "archived"


class BookshelfCollectionVisibility(StringEnum):
    PRIVATE = "private"
    SHARE_LINK = "share_link"


class CategoryStatus(StringEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class CategoryAssignmentSource(StringEnum):
    SYSTEM = "system"
    USER = "user"


class AgentMessageRole(StringEnum):
    USER = "user"
    ASSISTANT = "assistant"


class AgentStepKind(StringEnum):
    PLAN = "plan"
    TOOL = "tool"
    OBSERVE = "observe"
    ANSWER = "answer"


class AgentToolName(StringEnum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    TAGS = "tags"
    CATEGORIES = "categories"
    DOCUMENT_METADATA = "document_metadata"
    SOURCE_METADATA = "source_metadata"


class LLMProvider(StringEnum):
    OPENAI = "openai"
    DEEPSEEK = "deepseek"


class SourceProfileAnalysisStatus(StringEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class SourceProfileLinkKind(StringEnum):
    HOMEPAGE = "homepage"
    PROFILE = "profile"
    VISIBLE_LINK = "visible_link"
    EMAIL = "email"
