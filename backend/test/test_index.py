"""Unit tests for _index_data function."""

import pytest
from sqlalchemy import select

from app.dao.domain import get_domain_by_url, get_or_create_domain_by_url
from app.dao.link import get_link_by_url
from app.models.models import Domain, DomainMapping, Entry, Link, LinkMapping
from app.schemas.crawl import PageCrawlResult, PageLinks
from app.schemas.llm import EntryParseResult
from app.services.core import _index_data
from test.factories import DomainFactory, LinkFactory


@pytest.fixture
def sample_crawl_data():
    """Create sample crawl data for testing."""
    domain_url = "example.com"

    # Sample internal URLs
    internal_url1 = "https://example.com/page1"
    internal_url2 = "https://example.com/page2"
    internal_url3 = "https://example.com/page3"

    # Sample external URLs
    external_url1 = "https://external1.com/article"
    external_url2 = "https://external2.com/blog"

    # Create PageCrawlResult objects
    url_to_crawl_result = {
        internal_url1: PageCrawlResult(
            url=internal_url1,
            redirected_url=internal_url1,
            cleaned_html="<html><body>Page 1 content</body></html>",
            links=PageLinks(
                internal=[internal_url2, internal_url3],
                external=[external_url1],
            ),
        ),
        internal_url2: PageCrawlResult(
            url=internal_url2,
            redirected_url=internal_url2,
            cleaned_html="<html><body>Page 2 content</body></html>",
            links=PageLinks(
                internal=[internal_url1],
                external=[external_url2],
            ),
        ),
        internal_url3: PageCrawlResult(
            url=internal_url3,
            redirected_url=internal_url3,
            cleaned_html="<html><body>Page 3 content</body></html>",
            links=PageLinks(
                internal=[],
                external=[],
            ),
        ),
    }

    # Create EntryParseResult objects (only for some URLs)
    url_to_entry = {
        internal_url1: EntryParseResult(
            should_pursue=True,
            title="First Blog Post",
            summary="This is a summary of the first blog post",
            topics=["technology", "programming"],
            author="John Doe",
            date_published="2024-01-15",
        ),
        internal_url2: EntryParseResult(
            should_pursue=True,
            title="Second Blog Post",
            summary="This is a summary of the second blog post",
            topics=["design", "ui"],
            author="Jane Smith",
            date_published="2024-02-20",
        ),
    }

    return {
        "domain_url": domain_url,
        "url_to_crawl_result": url_to_crawl_result,
        "url_to_entry": url_to_entry,
        "expected_internal_urls": [internal_url1, internal_url2, internal_url3],
        "expected_external_urls": [external_url1, external_url2],
        "expected_external_domains": ["external1.com", "external2.com"],
    }


def test_index_data_creates_all_necessary_data(db_session, sample_crawl_data):
    """Test that _index_data creates all necessary data."""

    stmt = select(Entry)
    entries = db_session.execute(stmt).scalars().all()

    # Get or create domain in PENDING state
    domain = get_or_create_domain_by_url(sample_crawl_data["domain_url"])

    domain = _index_data(
        url_to_crawl_result=sample_crawl_data["url_to_crawl_result"],
        url_to_entry=sample_crawl_data["url_to_entry"],
        domain_url=sample_crawl_data["domain_url"],
        domain=domain,
    )

    # Verify domain was created
    assert domain is not None
    assert domain.domain_url == sample_crawl_data["domain_url"]
    assert domain.entity == "person"
    assert domain.name == "Unknown"

    db_domain = get_domain_by_url(sample_crawl_data["domain_url"])
    assert db_domain is not None
    assert db_domain.id == domain.id

    # Verify all internal links were created
    for url in sample_crawl_data["expected_internal_urls"]:
        link = get_link_by_url(url)
        assert link is not None, f"Link for {url} should exist"
        assert link.domain.domain_url == sample_crawl_data["domain_url"]

    # Verify all external links were created
    for url in sample_crawl_data["expected_external_urls"]:
        link = get_link_by_url(url)
        assert link is not None, f"External link for {url} should exist"
        assert link.domain.domain_url != sample_crawl_data["domain_url"]

    # Verify all external domains were created
    for domain_url in sample_crawl_data["expected_external_domains"]:
        ext_domain = get_domain_by_url(domain_url)
        assert ext_domain is not None, f"External domain {domain_url} should exist"
        assert ext_domain.entity == "unknown"
        assert ext_domain.name == "Unknown"

    # Verify entries were created
    stmt = select(Entry)
    entries = db_session.execute(stmt).scalars().all()
    assert len(entries) == len(sample_crawl_data["url_to_entry"])

    entry_urls = set(sample_crawl_data["url_to_entry"].keys())
    for entry in entries:
        assert entry.link.url in entry_urls
        assert entry.title is not None
        assert entry.summary is not None
        assert len(entry.topics) > 0
        assert entry.author is not None

    # Verify link mappings were created (internal -> external)
    stmt = select(LinkMapping)
    link_mappings = db_session.execute(stmt).scalars().all()
    assert len(link_mappings) >= 2  # At least page1->external1 and page2->external2

    # Verify specific mappings exist
    internal_url1 = "https://example.com/page1"
    internal_url2 = "https://example.com/page2"
    external_url1 = "https://external1.com/article"
    external_url2 = "https://external2.com/blog"

    source_link1 = get_link_by_url(internal_url1)
    source_link2 = get_link_by_url(internal_url2)
    target_link1 = get_link_by_url(external_url1)
    target_link2 = get_link_by_url(external_url2)

    mapping_ids = {
        (mapping.source_link_id, mapping.target_link_id) for mapping in link_mappings
    }
    assert source_link1 is not None
    assert source_link2 is not None
    assert target_link1 is not None
    assert target_link2 is not None
    
    assert (source_link1.id, target_link1.id) in mapping_ids
    assert (source_link2.id, target_link2.id) in mapping_ids

    # Verify domain mappings were created
    stmt = select(DomainMapping).where(DomainMapping.source_domain_id == domain.id)
    domain_mappings = db_session.execute(stmt).scalars().all()
    assert len(domain_mappings) == len(sample_crawl_data["expected_external_domains"])

    external_domain_ids = {
        get_domain_by_url(domain_url).id # type: ignore
        for domain_url in sample_crawl_data["expected_external_domains"]
    }
    mapped_target_ids = {mapping.target_domain_id for mapping in domain_mappings}
    assert mapped_target_ids == external_domain_ids


def test_index_data_handles_existing_domains(db_session, sample_crawl_data):
    """Test that _index_data handles existing domains correctly."""
    # Create an external domain using factory
    existing_domain = DomainFactory(
        domain_url="external1.com",
        entity="organization",
        name="Existing Domain",
    )
    db_session.commit()

    # Get or create domain in PENDING state
    domain = get_or_create_domain_by_url(sample_crawl_data["domain_url"])

    # Now run index_data
    _index_data(
        url_to_crawl_result=sample_crawl_data["url_to_crawl_result"],
        url_to_entry=sample_crawl_data["url_to_entry"],
        domain_url=sample_crawl_data["domain_url"],
        domain=domain,
    )

    # Verify existing domain was reused (not recreated)
    stmt = select(Domain).where(Domain.domain_url == "external1.com")
    domains = db_session.execute(stmt).scalars().all()
    assert len(domains) == 1
    assert domains[0].id == existing_domain.id
    assert domains[0].entity == "organization"  # Should keep original entity
    assert domains[0].name == "Existing Domain"  # Should keep original name


def test_index_data_handles_existing_links(db_session, sample_crawl_data):
    """Test that _index_data handles existing links correctly."""
    # Create domain and link using factories
    domain = DomainFactory(domain_url=sample_crawl_data["domain_url"])
    existing_link = LinkFactory(
        url="https://example.com/page1",
        domain=domain,
    )
    db_session.commit()

    # Get or create domain in PENDING state
    domain = get_or_create_domain_by_url(sample_crawl_data["domain_url"])

    # Now run index_data
    _index_data(
        url_to_crawl_result=sample_crawl_data["url_to_crawl_result"],
        url_to_entry=sample_crawl_data["url_to_entry"],
        domain_url=sample_crawl_data["domain_url"],
        domain=domain,
    )

    # Verify link was reused (not duplicated)
    stmt = select(Link).where(Link.url == "https://example.com/page1")
    links = db_session.execute(stmt).scalars().all()
    assert len(links) == 1
    assert links[0].id == existing_link.id


def test_index_data_deduplicates_external_links(db_session):
    """Test that _index_data deduplicates external links when multiple pages link to the same URL."""
    domain_url = "example.com"

    # Same external URL appears in multiple pages
    shared_external_url = "https://external.com/shared-article"

    internal_url1 = "https://example.com/page1"
    internal_url2 = "https://example.com/page2"
    internal_url3 = "https://example.com/page3"

    url_to_crawl_result = {
        internal_url1: PageCrawlResult(
            url=internal_url1,
            redirected_url=internal_url1,
            cleaned_html="<html><body>Page 1</body></html>",
            links=PageLinks(
                internal=[],
                external=[shared_external_url],
            ),
        ),
        internal_url2: PageCrawlResult(
            url=internal_url2,
            redirected_url=internal_url2,
            cleaned_html="<html><body>Page 2</body></html>",
            links=PageLinks(
                internal=[],
                external=[shared_external_url],  # Same external URL
            ),
        ),
        internal_url3: PageCrawlResult(
            url=internal_url3,
            redirected_url=internal_url3,
            cleaned_html="<html><body>Page 3</body></html>",
            links=PageLinks(
                internal=[],
                external=[shared_external_url],  # Same external URL again
            ),
        ),
    }

    url_to_entry = {}

    # Get or create domain in PENDING state
    domain = get_or_create_domain_by_url(domain_url)

    # Run index_data
    _index_data(
        url_to_crawl_result=url_to_crawl_result,
        url_to_entry=url_to_entry,
        domain_url=domain_url,
        domain=domain,
    )

    # Verify only ONE link was created for the shared external URL
    stmt = select(Link).where(Link.url == shared_external_url)
    links = db_session.execute(stmt).scalars().all()
    assert len(links) == 1, (
        f"Expected 1 link for {shared_external_url}, got {len(links)}"
    )

    shared_link = links[0]

    # Verify the link has the correct domain
    assert shared_link.domain.domain_url == "external.com"

    # Verify link mappings were created for all three pages -> shared external URL
    stmt = select(LinkMapping).where(LinkMapping.target_link_id == shared_link.id)
    mappings = db_session.execute(stmt).scalars().all()
    assert len(mappings) == 3, f"Expected 3 link mappings, got {len(mappings)}"

    # Verify all three internal pages have mappings to the shared external URL
    source_link_ids = {mapping.source_link_id for mapping in mappings}
    internal_link1 = get_link_by_url(internal_url1)
    internal_link2 = get_link_by_url(internal_url2)
    internal_link3 = get_link_by_url(internal_url3)

    assert internal_link1 is not None
    assert internal_link2 is not None
    assert internal_link3 is not None

    assert internal_link1.id in source_link_ids
    assert internal_link2.id in source_link_ids
    assert internal_link3.id in source_link_ids
