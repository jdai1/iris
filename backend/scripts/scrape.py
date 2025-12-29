"""Scrape command functions."""

# Initialize custom logger before importing other modules
from app.utils.logger import scraper_logger  # noqa: F401

from app.dao.domain import get_domain_by_url, reset_domain_status
from app.enums.core import DomainStatus
from app.services.core import scrape_domain
from app.utils.db_utils import print_domain_state
from app.utils.url_utils import get_domain


def scrape_domain_cmd(url: str, max_depth: int = 10, batch_size: int = 50) -> None:
    """Scrape a domain and display the results."""
    print(f"\n🚀 Starting scrape for: {url}")
    print(f"   Max depth: {max_depth}")
    print(f"   Batch size: {batch_size}\n")

    # Check domain status before scraping
    domain_url = get_domain(url)
    domain = get_domain_by_url(domain_url)

    if domain and domain.status != DomainStatus.PENDING:
        print(f"\n⚠️  WARNING: Domain '{domain_url}' is not in PENDING state.")
        print(f"   Current status: {domain.status.value}")
        if domain.error_message:
            print(f"   Error message: {domain.error_message}")
        print("\n   Scraping will update existing entries and may overwrite data.")
        response = input("\n❓ Are you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Scraping cancelled")
            return
        print()

        reset_domain_status(domain=domain, status=DomainStatus.PENDING)

    # Run the scraper
    scrape_domain(
        url=url,
        max_depth=max_depth,
        batch_size=batch_size,
    )

    # Display results
    print_domain_state(domain_url)

    print("✅ Scraping completed successfully!")
