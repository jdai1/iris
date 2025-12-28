import aiohttp
import pytest

from app.services.core import _crawl_pages
from app.utils.url_utils import get_domain


@pytest.mark.asyncio
async def test_crawl_pages():
    """Test that _crawl_pages returns expected structure and properties."""
    test_url = "https://jdai1.github.io"
    domain_url = get_domain(test_url)

    async with aiohttp.ClientSession() as session:
        # Run crawl
        url_to_crawl_result = await _crawl_pages(
            http_session=session,
            start_url=test_url,
            domain_url=domain_url,
            max_depth=3,  # Limit depth for testing
            batch_size=5,  # Smaller batch size for testing
        )

    for url, crawl_result in url_to_crawl_result.items():
        print(f"URL: {url}")
        print(f"Redirected URL: {crawl_result.redirected_url}")
        print(f"Links: {crawl_result.links}")

    breakpoint()
