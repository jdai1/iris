"""Database utility functions for inspecting scraped data."""

from sqlalchemy import select

import app.db as db
from app.models.models import (
    Domain,
    DomainMapping,
    Entry,
    Link,
    LinkMapping,
)
from app.utils.url_utils import get_domain


def print_domain_state(domain_url: str) -> None:
    """
    Print the database state for a single domain.

    Args:
        domain_url: The domain URL to inspect (e.g., "jdai1.github.io" or "https://jdai1.github.io")
    """
    # Normalize domain URL (remove protocol, www, etc.)
    domain_url = get_domain(domain_url)

    print("\n" + "=" * 80)
    print(f"DATABASE STATE FOR: {domain_url}")
    print("=" * 80)

    # Get domain
    stmt = select(Domain).where(Domain.domain_url == domain_url)
    domain = db.session.execute(stmt).scalar_one_or_none()

    if not domain:
        print(f"\n❌ Domain '{domain_url}' not found in database")
        print("=" * 80 + "\n")
        return

    print("\n📁 DOMAIN:")
    print(f"  - {domain.domain_url}")
    print(f"    ID: {domain.id}")
    print(f"    Entity: {domain.entity}, Name: {domain.name}")
    print(f"    Status: {domain.status.value}")
    if domain.error_message:
        print(f"    Error: {domain.error_message}")

    # Links and Entries for this domain (combined)
    stmt = select(Link).where(Link.domain_id == domain.id)
    links = db.session.execute(stmt).scalars().all()

    # Get entries keyed by link_id for quick lookup
    entries_stmt = select(Entry).join(Link).where(Link.domain_id == domain.id)
    entries = db.session.execute(entries_stmt).scalars().all()
    entries_by_link_id = {entry.link_id: entry for entry in entries}

    # Separate links into those with and without entries
    links_with_entries = []
    links_without_entries = []
    for link in links:
        if link.id in entries_by_link_id:
            links_with_entries.append((link, entries_by_link_id[link.id]))
        else:
            links_without_entries.append(link)

    print(f"\n🔗 LINKS & ENTRIES ({len(links)} links, {len(entries)} entries):")

    # Print links without entries first
    for link in links_without_entries:
        print(f"  ⚪ {link.url} (no entry)")

    # Print links with entries
    for link, entry in links_with_entries:
        print(f"  • {link.url}")
        print(f"     Title: {entry.title[:60]}...")
        print(f"     Author: {entry.author}")
        print(f"     Topics: {', '.join(entry.topics[:5])}")
        if entry.date_published:
            print(f"     Published: {entry.date_published}")
        if entry.embedding is not None and len(entry.embedding) > 0:
            print(f"     Has embedding ({len(entry.embedding)} dimensions)")

    # Link Mappings (internal -> external) for this domain
    stmt = (
        select(LinkMapping)
        .join(Link, LinkMapping.source_link_id == Link.id)
        .where(Link.domain_id == domain.id)
    )
    link_mappings = db.session.execute(stmt).scalars().all()
    print(f"\n🔗→🔗 LINK MAPPINGS ({len(link_mappings)}):")
    for mapping in link_mappings:
        source_link = db.session.get(Link, mapping.source_link_id)
        target_link = db.session.get(Link, mapping.target_link_id)
        if source_link and target_link:
            print(f"  - {source_link.url[:50]}... → {target_link.url[:50]}...")

    # Domain Mappings (this domain -> other domains)
    stmt = select(DomainMapping).where(DomainMapping.source_domain_id == domain.id)
    domain_mappings = db.session.execute(stmt).scalars().all()
    print(f"\n📁→📁 DOMAIN MAPPINGS ({len(domain_mappings)}):")
    for mapping in domain_mappings:
        target_domain = db.session.get(Domain, mapping.target_domain_id)
        if target_domain:
            print(f"  - {domain.domain_url} → {target_domain.domain_url}")

    print("\n" + "=" * 80 + "\n")
