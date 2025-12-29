"""Database command functions."""

from sqlalchemy import select

import app.db as db
from app.enums.core import DomainStatus
from app.models.models import (
    Domain,
    DomainMapping,
    Entry,
    Link,
    LinkMapping,
)
from app.utils.url_utils import get_domain


def reset_domain(domain_url: str, confirm: bool = False) -> None:
    """
    Delete scraped data for a domain and reset its status to PENDING.

    Deletes:
    - Entries for this domain
    - Link mappings where source_link belongs to this domain
    - Links for this domain
    - Domain mappings where this domain is the source

    Resets:
    - Domain status to PENDING
    - Domain error_message to None

    Args:
        domain_url: The domain URL to reset (e.g., "jdai1.github.io" or "https://jdai1.github.io")
        confirm: If False, will prompt for confirmation before deleting
    """
    # Normalize domain URL
    domain_url = get_domain(domain_url)

    # Get domain
    stmt = select(Domain).where(Domain.domain_url == domain_url)
    domain = db.session.execute(stmt).scalar_one_or_none()

    if not domain:
        print(f"\n❌ Domain '{domain_url}' not found in database")
        return

    # Show what will be deleted
    print(f"\n⚠️  WARNING: This will delete scraped data for '{domain_url}':")

    # Count related data
    links_stmt = select(Link).where(Link.domain_id == domain.id)
    links = db.session.execute(links_stmt).scalars().all()
    print(f"   - Links: {len(links)}")

    entries_stmt = select(Entry).join(Link).where(Link.domain_id == domain.id)
    entries = db.session.execute(entries_stmt).scalars().all()
    print(f"   - Entries: {len(entries)}")

    link_mappings_stmt = (
        select(LinkMapping)
        .join(Link, LinkMapping.source_link_id == Link.id)
        .where(Link.domain_id == domain.id)
    )
    link_mappings = db.session.execute(link_mappings_stmt).scalars().all()
    print(f"   - Link Mappings: {len(link_mappings)}")

    # Only domain mappings where this domain is the source
    domain_mappings_stmt = select(DomainMapping).where(
        DomainMapping.source_domain_id == domain.id
    )
    domain_mappings = db.session.execute(domain_mappings_stmt).scalars().all()
    print(f"   - Domain Mappings (as source): {len(domain_mappings)}")

    print(f"\n   Domain status will be reset to: {DomainStatus.PENDING.value}")

    if not confirm:
        response = input("\n❓ Are you sure you want to delete this data? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Reset cancelled")
            return

    print("\n🗑️  Deleting scraped data...")

    # Delete in order (respecting foreign key constraints)
    # 1. Entries
    for entry in entries:
        db.session.delete(entry)
    print(f"   ✓ Deleted {len(entries)} entries")

    # 2. Link Mappings (where source_link belongs to this domain)
    for mapping in link_mappings:
        db.session.delete(mapping)
    print(f"   ✓ Deleted {len(link_mappings)} link mappings")

    # 3. Links
    for link in links:
        db.session.delete(link)
    print(f"   ✓ Deleted {len(links)} links")

    # 4. Domain Mappings (where this domain is the source)
    for mapping in domain_mappings:
        db.session.delete(mapping)
    print(f"   ✓ Deleted {len(domain_mappings)} domain mappings")

    # 5. Reset domain status
    domain.status = DomainStatus.PENDING
    domain.error_message = None
    print(f"   ✓ Reset domain status to {DomainStatus.PENDING.value}")

    # Commit transaction
    db.session.commit()
    print(f"\n✅ Domain '{domain_url}' reset successfully!")
