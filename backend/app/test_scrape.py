from services.core import scrape_domain


def test_scrape_jdai1_github_io():
    """Test scraping jdai1.github.io end-to-end."""
    test_url = "https://jdai1.github.io"
    
    # Run the scrape
    scrape_domain(
        url=test_url,
        max_depth=3,  # Limit depth for testing
        batch_size=5,  # Smaller batch size for testing
    )

test_scrape_jdai1_github_io()