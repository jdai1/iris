import aiohttp
import pytest

from app.services.llm_services import parse_entry
from app.utils.scrape_utils import crawl_url


@pytest.mark.asyncio
async def test_quote_page_not_classified_as_entry():
    """Test that a quote/media page is correctly identified as NOT an entry."""
    test_url = "https://jdai1.github.io/media/chesky"

    # This is a quote page with:
    # - "← Back to Media" navigation
    # - Attribution "- Brian Chesky" at the end
    # - It's displaying someone else's words
    # Should NOT be classified as an entry (should_pursue=False)

    async with aiohttp.ClientSession() as session:
        # Crawl the URL to get HTML
        crawl_result = await crawl_url(session, test_url)

        # Parse entry using the classifier
        parse_result = await parse_entry(
            url=crawl_result.redirected_url, html=crawl_result.cleaned_html
        )

        # Assert that this quote page is NOT classified as an entry
        assert not parse_result.should_pursue, (
            "Expected should_pursue=False for quote/media page, but got True. "
            "This page has 'Back to Media' navigation and attribution '- Brian Chesky', "
            "so it should be excluded as a quote/media page."
        )
