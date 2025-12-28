"""Tests for domain classification."""

import pytest
from openai import AsyncOpenAI
import os

from app.services.llm_services import classify_domain
from app.utils.scrape_utils import crawl_url
import aiohttp


@pytest.fixture
async def openai_client():
    """Create OpenAI client for testing."""
    client = AsyncOpenAI(api_key=os.getenv("PERSONAL_OPENAI_API_KEY"))
    yield client
    await client.close()


# Test cases: (domain, expected_is_blog)
# Ground truth guesses - user will correct these
DOMAIN_TEST_CASES = [
    ("jdai1.github.io", True),
    ("noahrousell.com", True),
    ("goranshbharal.substack.com", True),  # Substack blog
    ("paulgraham.com", True),  # Paul Graham's blog
    ("dof.brown.edu", False),  # University department
    ("arc.net", False),  # Company website
    ("noahrousell.com", True),  # Personal blog
    ("youtube.com", False),  # Video platform
    ("linkedin.com", False),  # Social network
    ("harrypotter.fandom.com", False),  # Wiki/fandom site
    ("herman.bearblog.dev", True),  # Bearblog blog
    ("benkuhn.net", True),  # Personal blog
    ("chromewebstore.google.com", False),  # Web store
    ("archive.org", False),  # Archive site
    ("markmanson.net", True),  # Author/blog
    ("shop.pavlok.com", False),  # E-commerce shop
    ("rescuetime.com", False),  # Product/service site
    ("guzey.com", True),  # Personal blog
    ("dair.ai", False),  # Educational
    ("burntoutatbrown.com", False),  # Misc
    ("brown.edu", False),  # University
    ("ramp.com", False),  # Company
    ("plan-my-day.vercel.app", False),  # App
    ("fs.blog", True),  # Personal blog
    ("milkov.tech", True),  # Personal blog
    ("youngkim.co", True),  # Personal blog
    ("patrickcollison.com", True),  # Personal blog
]


@pytest.mark.asyncio
@pytest.mark.parametrize("domain,expected_is_blog", DOMAIN_TEST_CASES)
async def test_domain_classification(openai_client, domain, expected_is_blog):
    """Test that domain classification correctly identifies blogs."""
    # Construct URL
    url = f"https://{domain}"

    # Fetch HTML
    async with aiohttp.ClientSession() as http_session:
        crawl_result = await crawl_url(http_session, url)
        html = crawl_result.cleaned_html

    # Classify domain
    result = await classify_domain(url=url, html=html, client=openai_client)

    # Verify blog classification
    assert result.blog == expected_is_blog, (
        f"Domain {domain}: expected blog={expected_is_blog}, got blog={result.blog}. "
        f"Entity: {result.entity}, Name: {result.name}"
    )

    print(f"✓ {domain}: blog={result.blog}, entity={result.entity}, name={result.name}")
