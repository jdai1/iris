"""End-to-end test for indexing a domain."""

from sqlalchemy import select

from app.enums.core import DomainStatus
from app.models.models import (
    Domain,
    DomainMapping,
    Entry,
    Link,
    LinkMapping,
)
from app.services.core import scrape_domain


def print_db_state(session):
    """Print the current state of the database."""
    print("\n" + "=" * 80)
    print("DATABASE STATE")
    print("=" * 80)

    # Domains
    stmt = select(Domain)
    domains = session.execute(stmt).scalars().all()
    print(f"\n📁 DOMAINS ({len(domains)}):")
    for domain in domains:
        print(f"  - {domain.domain_url}")
        print(f"    ID: {domain.id}")
        print(f"    Entity: {domain.entity}, Name: {domain.name}")
        print(f"    Status: {domain.status.value}")
        if domain.error_message:
            print(f"    Error: {domain.error_message}")

    # Links
    stmt = select(Link)
    links = session.execute(stmt).scalars().all()
    print(f"\n🔗 LINKS ({len(links)}):")
    for link in links:
        print(f"  - {link.url}")
        print(f"    ID: {link.id}")
        print(f"    Domain: {link.domain.domain_url}")

    # Entries
    stmt = select(Entry)
    entries = session.execute(stmt).scalars().all()
    print(f"\n📝 ENTRIES ({len(entries)}):")
    for entry in entries:
        print(f"  - {entry.link.url}")
        print(f"    Title: {entry.title[:60]}...")
        print(f"    Author: {entry.author}")
        print(f"    Topics: {', '.join(entry.topics[:5])}")
        if entry.date_published:
            print(f"    Published: {entry.date_published}")

    # Link Mappings
    stmt = select(LinkMapping)
    link_mappings = session.execute(stmt).scalars().all()
    print(f"\n🔗→🔗 LINK MAPPINGS ({len(link_mappings)}):")
    for mapping in link_mappings:
        source_link = session.get(Link, mapping.source_link_id)
        target_link = session.get(Link, mapping.target_link_id)
        if source_link and target_link:
            print(f"  - {source_link.url[:50]}... → {target_link.url[:50]}...")

    # Domain Mappings
    stmt = select(DomainMapping)
    domain_mappings = session.execute(stmt).scalars().all()
    print(f"\n📁→📁 DOMAIN MAPPINGS ({len(domain_mappings)}):")
    for mapping in domain_mappings:
        source_domain = session.get(Domain, mapping.source_domain_id)
        target_domain = session.get(Domain, mapping.target_domain_id)
        if source_domain and target_domain:
            print(f"  - {source_domain.domain_url} → {target_domain.domain_url}")

    print("\n" + "=" * 80 + "\n")


def test_index_jdai1_github_io(db_session):
    """E2E test: Index jdai1.github.io and print database state."""
    # Index the domain
    scrape_domain(
        url="https://jdai1.github.io",
        max_depth=3,  # Limit depth for faster testing
        batch_size=10,  # Smaller batch size for testing
    )

    # Print database state
    print_db_state(db_session)

    # Verify some basic expectations
    stmt = select(Domain).where(Domain.domain_url == "jdai1.github.io")
    domain = db_session.execute(stmt).scalar_one_or_none()
    assert domain is not None, "Domain should be created"

    # Verify links exist
    stmt = select(Link).join(Domain).where(Domain.domain_url == "jdai1.github.io")
    links = db_session.execute(stmt).scalars().all()
    assert len(links) > 0, "Should have at least some links"

    print("✅ E2E test completed successfully!")

    breakpoint()


def test_scrape_forbidden_site(db_session):
    """E2E test: Attempt to scrape a site that forbids scraping (gmail.com)."""
    # Attempt to scrape gmail.com (which forbids scraping)
    scrape_domain(
        url="https://en.wikipedia.org",
        max_depth=1,
        batch_size=10,
    )

    # Verify domain was created with SCRAPING_FAILED status
    stmt = select(Domain).where(Domain.domain_url == "en.wikipedia.org")
    domain = db_session.execute(stmt).scalar_one_or_none()

    assert domain is not None, "Domain should be created even if scraping fails"
    assert domain.status == DomainStatus.SCRAPING_FAILED, (
        f"Domain status should be SCRAPING_FAILED, got {domain.status.value}"
    )
    assert domain.error_message is not None, "Domain should have an error message"


def test_rescrape_preserves_links(db_session):
    """Test that rescraping preserves links but updates entries."""
    from app.dao.link import get_link_by_url
    from app.schemas.crawl import PageCrawlResult, PageLinks
    from app.schemas.llm import EntryWithEmbedding
    from app.services.core import _index_data
    from test.factories import DomainFactory, EntryFactory, LinkFactory

    domain_url = "test-rescrape.com"
    domain = DomainFactory(domain_url=domain_url, status=DomainStatus.SUCCESS)

    # Create initial links
    link1 = LinkFactory(url="https://test-rescrape.com/page1", domain=domain)
    link2 = LinkFactory(url="https://test-rescrape.com/page2", domain=domain)
    link3 = LinkFactory(url="https://test-rescrape.com/page3", domain=domain)

    # Create initial entries for link1 and link2
    EntryFactory(
        link=link1,
        title="Old Title 1",
        summary="Old summary 1",
        author="Old Author 1",
    )
    EntryFactory(
        link=link2,
        title="Old Title 2",
        summary="Old summary 2",
        author="Old Author 2",
    )

    db_session.flush()

    # Rescrape: page1 and page2 still have entries (but different content)
    # page3 now has an entry (new entry)
    # (link3 still exists but no entry for it in first scrape)
    url_to_crawl_result = {
        "https://test-rescrape.com/page1": PageCrawlResult(
            url="https://test-rescrape.com/page1",
            redirected_url="https://test-rescrape.com/page1",
            cleaned_html="<html><body>Page 1 updated content</body></html>",
            links=PageLinks(internal=[], external=[]),
        ),
        "https://test-rescrape.com/page2": PageCrawlResult(
            url="https://test-rescrape.com/page2",
            redirected_url="https://test-rescrape.com/page2",
            cleaned_html="<html><body>Page 2 updated content</body></html>",
            links=PageLinks(internal=[], external=[]),
        ),
        "https://test-rescrape.com/page3": PageCrawlResult(
            url="https://test-rescrape.com/page3",
            redirected_url="https://test-rescrape.com/page3",
            cleaned_html="<html><body>Page 3 content</body></html>",
            links=PageLinks(internal=[], external=[]),
        ),
    }

    # Mock entries: page1 and page2 have updated entries, page3 has new entry
    url_to_entry = {
        "https://test-rescrape.com/page1": EntryWithEmbedding(
            should_pursue=True,
            title="New Title 1",
            summary="New summary 1",
            topics=["new", "topics"],
            author="New Author 1",
            date_published="2024-01-01",
            embedding=[0.1] * 1536,
        ),
        "https://test-rescrape.com/page2": EntryWithEmbedding(
            should_pursue=True,
            title="New Title 2",
            summary="New summary 2",
            topics=["different", "topics"],
            author="New Author 2",
            date_published="2024-01-02",
            embedding=[0.2] * 1536,
        ),
        "https://test-rescrape.com/page3": EntryWithEmbedding(
            should_pursue=True,
            title="New Title 3",
            summary="New summary 3",
            topics=["fresh", "topics"],
            author="New Author 3",
            date_published="2024-01-03",
            embedding=[0.3] * 1536,
        ),
    }

    # Rescrape
    _index_data(
        url_to_crawl_result=url_to_crawl_result,
        url_to_entry=url_to_entry,
        domain_url=domain_url,
        domain=domain,
    )

    db_session.flush()

    # Verify links are preserved (same IDs)
    link1_after = get_link_by_url("https://test-rescrape.com/page1")
    link2_after = get_link_by_url("https://test-rescrape.com/page2")
    link3_after = get_link_by_url("https://test-rescrape.com/page3")

    assert link1_after is not None
    assert link2_after is not None
    assert link3_after is not None
    assert link1_after.id == link1.id, "Link1 ID should be preserved"
    assert link2_after.id == link2.id, "Link2 ID should be preserved"
    assert link3_after.id == link3.id, "Link3 ID should be preserved"

    # Verify new entries exist with updated content
    stmt = select(Entry).join(Link).where(Link.domain_id == domain.id)
    all_entries = db_session.execute(stmt).scalars().all()
    assert len(all_entries) == 3, "Should have 3 entries after rescrape"

    entry_by_url = {entry.link.url: entry for entry in all_entries}
    assert entry_by_url["https://test-rescrape.com/page1"].title == "New Title 1"
    assert entry_by_url["https://test-rescrape.com/page1"].author == "New Author 1"
    assert entry_by_url["https://test-rescrape.com/page2"].title == "New Title 2"
    assert entry_by_url["https://test-rescrape.com/page2"].author == "New Author 2"
    assert entry_by_url["https://test-rescrape.com/page3"].title == "New Title 3"
    assert entry_by_url["https://test-rescrape.com/page3"].author == "New Author 3"

    # Verify entry IDs are different from old ones (new entries created)
    # Old entries should be deleted, so we can't query them directly
    # But we can verify the new entries have different content
    assert entry_by_url["https://test-rescrape.com/page1"].title != "Old Title 1"
    assert entry_by_url["https://test-rescrape.com/page2"].title != "Old Title 2"


def test_rescrape_deletes_orphaned_entries(db_session):
    """Test that rescraping deletes entries for links that no longer have entries."""
    from app.dao.link import get_link_by_url
    from app.schemas.crawl import PageCrawlResult, PageLinks
    from app.schemas.llm import EntryWithEmbedding
    from app.services.core import _index_data
    from test.factories import DomainFactory, EntryFactory, LinkFactory

    domain_url = "test-orphan.com"
    domain = DomainFactory(domain_url=domain_url, status=DomainStatus.SUCCESS)

    # Create initial links
    link1 = LinkFactory(url="https://test-orphan.com/page1", domain=domain)
    link2 = LinkFactory(url="https://test-orphan.com/page2", domain=domain)
    link3 = LinkFactory(url="https://test-orphan.com/page3", domain=domain)

    # Create initial entries for all three links
    EntryFactory(link=link1, title="Entry 1")
    EntryFactory(link=link2, title="Entry 2")
    entry3 = EntryFactory(link=link3, title="Entry 3")

    db_session.flush()

    # Rescrape: only page1 and page2 have entries now (page3 no longer has entry)
    url_to_crawl_result = {
        "https://test-orphan.com/page1": PageCrawlResult(
            url="https://test-orphan.com/page1",
            redirected_url="https://test-orphan.com/page1",
            cleaned_html="<html><body>Page 1</body></html>",
            links=PageLinks(internal=[], external=[]),
        ),
        "https://test-orphan.com/page2": PageCrawlResult(
            url="https://test-orphan.com/page2",
            redirected_url="https://test-orphan.com/page2",
            cleaned_html="<html><body>Page 2</body></html>",
            links=PageLinks(internal=[], external=[]),
        ),
        "https://test-orphan.com/page3": PageCrawlResult(
            url="https://test-orphan.com/page3",
            redirected_url="https://test-orphan.com/page3",
            cleaned_html="<html><body>Page 3</body></html>",
            links=PageLinks(internal=[], external=[]),
        ),
    }

    # Only page1 and page2 have entries (page3 is orphaned)
    url_to_entry = {
        "https://test-orphan.com/page1": EntryWithEmbedding(
            should_pursue=True,
            title="Updated Entry 1",
            summary="Updated summary 1",
            topics=["topic1"],
            author="Author 1",
            date_published="2024-01-01",
            embedding=[0.1] * 1536,
        ),
        "https://test-orphan.com/page2": EntryWithEmbedding(
            should_pursue=True,
            title="Updated Entry 2",
            summary="Updated summary 2",
            topics=["topic2"],
            author="Author 2",
            date_published="2024-01-02",
            embedding=[0.2] * 1536,
        ),
        # page3 is NOT in url_to_entry - it should be orphaned
    }

    # Rescrape
    _index_data(
        url_to_crawl_result=url_to_crawl_result,
        url_to_entry=url_to_entry,
        domain_url=domain_url,
        domain=domain,
    )

    db_session.flush()

    # Verify links are still preserved
    link1_after = get_link_by_url("https://test-orphan.com/page1")
    link2_after = get_link_by_url("https://test-orphan.com/page2")
    link3_after = get_link_by_url("https://test-orphan.com/page3")

    assert link1_after is not None
    assert link2_after is not None
    assert link3_after is not None

    # Verify entry3 (orphaned) is deleted
    stmt = select(Entry).where(Entry.id == entry3.id)
    orphaned_entry = db_session.execute(stmt).scalar_one_or_none()
    assert orphaned_entry is None, "Orphaned entry should be deleted"

    # Verify entries for page1 and page2 exist (updated)
    stmt = select(Entry).join(Link).where(Link.domain_id == domain.id)
    all_entries = db_session.execute(stmt).scalars().all()
    assert len(all_entries) == 2, (
        "Should have 2 entries after rescrape (page3 orphaned)"
    )

    entry_by_url = {entry.link.url: entry for entry in all_entries}
    assert "https://test-orphan.com/page1" in entry_by_url
    assert "https://test-orphan.com/page2" in entry_by_url
    assert "https://test-orphan.com/page3" not in entry_by_url

    # Verify page3 link exists but has no entry
    assert link3_after.entry is None, "Link3 should exist but have no entry"
