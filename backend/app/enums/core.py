"""Core enums for the application."""

import enum


class DomainStatus(str, enum.Enum):
    """Status of a domain scraping attempt."""

    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    SCRAPING_FAILED = "SCRAPING_FAILED"
    NOT_A_BLOG = "NOT_A_BLOG"
    OTHER_FAILURE = "OTHER_FAILURE"


class EntityType(str, enum.Enum):
    """Type of entity represented by a domain."""

    PERSON = "person"
    COMPANY = "company"
    ORGANIZATION = "organization"
    GOVERNMENT = "government"
    SCHOOL = "school"
    UNKNOWN = "unknown"
    OTHER = "other"
