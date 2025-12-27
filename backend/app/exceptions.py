class FatalException(Exception):
    """Unrecoverable error during domain crawling."""

    pass


class SkipCrawlingDomainException(Exception):
    """Domain should be skipped (already scraped, excluded, or invalid)."""

    pass


class TooManyCrawlingTimeoutsException(Exception):
    """Too many timeouts occurred during crawling."""

    pass


class TooManyInternalLinksException(Exception):
    """Too many internal links to process."""

    pass
