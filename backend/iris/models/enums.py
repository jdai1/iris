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


class DigestStatus(StringEnum):
    QUEUED = "queued"
    SHOWN = "shown"
    SAVED = "saved"
    DISMISSED = "dismissed"
    SKIPPED = "skipped"


class FeedbackAction(StringEnum):
    SAVE = "save"
    DISMISS = "dismiss"
    SKIP = "skip"
    OPEN = "open"
    READ = "read"
    LIKE = "like"


class FeedbackSurface(StringEnum):
    SEARCH = "search"
    DIGEST = "digest"
    SOURCE_QUEUE = "source_queue"
    DOCUMENT = "document"
