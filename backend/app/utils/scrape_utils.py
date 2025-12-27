from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from constants import PAGE_TIMEOUT_MS
from exceptions import FatalException
from schemas.crawl import PageCrawlResult, PageLinks
from utils.url_utils import add_https_if_missing, is_external_link, sanitize_url


async def crawl_url(
    session: aiohttp.ClientSession, url: str, timeout_ms: int = PAGE_TIMEOUT_MS
) -> PageCrawlResult:
    """
    Crawl a URL and return PageCrawlResult with HTML and links.

    Returns:
        PageCrawlResult with url, redirected_url, cleaned_html, and links
    """
    try:
        original_url = sanitize_url(url)
        html, redirected_url = await fetch_html(
            session, original_url, timeout=timeout_ms / 1000
        )
        redirected_url = sanitize_url(redirected_url)

        # Extract links from HTML
        all_links = extract_links_from_html(html, redirected_url)

        # Categorize links into internal and external based on domain
        internal_links = []
        external_links = []

        for link in all_links:
            if is_external_link(link, redirected_url):
                external_links.append(link)
            else:
                internal_links.append(link)

        links = PageLinks(
            internal=internal_links,
            external=external_links,
        )

        return PageCrawlResult(
            url=original_url,
            redirected_url=redirected_url,
            cleaned_html=html,
            links=links,
        )
    except FatalException:
        raise
    except Exception as e:
        raise FatalException(f"Crawling {url} failed with error: {str(e)}") from e


async def fetch_html(
    session: aiohttp.ClientSession, url: str, timeout: int = 10
) -> tuple[str, str]:
    """
    Fetch HTML from URL with redirect handling.

    Returns:
        (html_content, final_url_after_redirects)
    """
    try:
        url = add_https_if_missing(url)
        async with session.get(url, allow_redirects=True, timeout=timeout) as response:
            response.raise_for_status()
            html = await response.text()
            final_url = str(response.url)
            return html, final_url
    except Exception as e:
        raise FatalException(f"Failed to fetch {url}: {str(e)}") from e


def extract_links_from_html(html: str, base_url: str) -> list[str]:
    """
    Extract all href links from HTML.

    Returns:
        List of absolute URLs
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        absolute_url = urljoin(base_url, href)
        links.append(absolute_url)

    return links


def extract_links_from_crawl_result(
    crawl_result: PageCrawlResult,
) -> tuple[list[str], list[str]]:
    """
    Extract internal and external links from PageCrawlResult.

    Returns:
        (internal_links, external_links)
    """
    internal_links = [sanitize_url(link) for link in crawl_result.links.internal]
    external_links = [sanitize_url(link) for link in crawl_result.links.external]
    return internal_links, external_links
