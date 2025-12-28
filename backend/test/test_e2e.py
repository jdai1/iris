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
