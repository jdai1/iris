import aiohttp
import pytest

from app.services.llm_services import parse_entry
from app.utils.scrape_utils import crawl_url
from openai import AsyncOpenAI
import os


@pytest.fixture
async def openai_client():
    client = AsyncOpenAI(api_key=os.getenv("PERSONAL_OPENAI_API_KEY"))
    yield client
    await client.close()  # important


@pytest.mark.asyncio
async def test_quote_page_not_classified_as_entry(openai_client):
    test_url = "https://jdai1.github.io/media/bluelock"

    async with aiohttp.ClientSession() as session:
        # Crawl the URL to get HTML
        crawl_result = await crawl_url(session, test_url)

        # Parse entry using the classifier
        parse_result = await parse_entry(
            url=crawl_result.redirected_url,
            html=crawl_result.cleaned_html,
            client=openai_client,
        )
        breakpoint()
        # Assert that this quote page is NOT classified as an entry
        assert not parse_result.should_pursue, (
            "Expected should_pursue=False for quote/media page, but got True. "
            "This page has 'Back to Media' navigation and attribution '- Brian Chesky', "
            "so it should be excluded as a quote/media page."
        )
