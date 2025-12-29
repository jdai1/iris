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

@pytest.mark.parametrize(("test_url", "expected_should_pursue"), [
    ("https://rkg.blog", False)
])
@pytest.mark.asyncio
async def test_quote_page_not_classified_as_entry(openai_client: AsyncOpenAI, test_url: str, expected_should_pursue: bool):
    async with aiohttp.ClientSession() as session:
        # Crawl the URL to get HTML
        crawl_result = await crawl_url(session, test_url)

        # Parse entry using the classifier
        parse_result = await parse_entry(
            url=crawl_result.redirected_url,
            html=crawl_result.cleaned_html,
            client=openai_client,
        )
        assert not parse_result.should_pursue
