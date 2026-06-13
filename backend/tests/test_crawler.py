from __future__ import annotations

import asyncio
import httpx
import pytest
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from iris.services.ingestion import crawler as crawler_module
from iris.services.ingestion.crawler import Crawler, PagePipelineResult
from iris.models import CrawlJob, Document, Link, Source
from iris.dao.sources import get_or_create_source
from iris.schemas.ingestion import ExtractedLink, ExtractedPage, FetchResult


@pytest.fixture(autouse=True)
def deterministic_page_pipeline(monkeypatch):
    """Keep crawler tests focused on crawl mechanics, not live LLM output."""

    async def fake_extract_page_async(html: str, final_url: str) -> ExtractedPage:
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(" ", strip=True) if title_tag else None
        text = soup.get_text(" ", strip=True)
        links = [
            ExtractedLink(
                url=urljoin(final_url, str(anchor.get("href") or "")),
                anchor_text=anchor.get_text(" ", strip=True),
                context="",
            )
            for anchor in soup.find_all("a")
        ]
        document_type = "essay" if len(text.split()) >= 20 else "ignore"
        return ExtractedPage(
            title=title,
            author=None,
            published_at=None,
            text=text,
            summary=text[:200],
            topics=["test"],
            document_type=document_type,
            category_slug=None,
            links=links,
        )

    async def fake_embed_text_async(_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(crawler_module, "extract_page_async", fake_extract_page_async)
    monkeypatch.setattr(crawler_module, "embed_text_async", fake_embed_text_async)


def client_for_fixture() -> httpx.Client:
    pages = {
        "https://a.test/": """
            <html><head><title>A Home</title></head><body>
            <article>""" + " ".join(["Home essay about research taste."] * 60) + """</article>
            <a href="/one">One</a>
            <a href="/two">Two</a>
            <a href="https://b.test/">B</a>
            <a href="https://www.youtube.com/watch?v=abc">Video</a>
            <a href="https://en.wikipedia.org/wiki/Test">Reference</a>
            </body></html>
        """,
        "https://a.test/one": """
            <html><head><title>One</title></head><body>
            <article>""" + " ".join(["Small teams coordination learning."] * 80) + """</article>
            <a href="/two">Two again</a><a href="/deep">Deep</a>
            </body></html>
        """,
        "https://a.test/two": """
            <html><head><title>Two</title></head><body>
            <article>""" + " ".join(["Essays search discovery media."] * 80) + """</article>
            <a href="/one">Cycle</a>
            </body></html>
        """,
        "https://a.test/deep": """
            <html><head><title>Deep</title></head><body>
            <article>""" + " ".join(["This should not be reached at depth one."] * 80) + """</article>
            </body></html>
        """,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in pages:
            return httpx.Response(200, text=pages[url], headers={"content-type": "text/html"}, request=request)
        return httpx.Response(404, text="not found", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def client_for_feed_and_sitemap_fixture() -> httpx.Client:
    pages = {
        "https://archive.test/": """
            <html><head>
            <link rel="alternate" type="application/atom+xml" href="/feed.xml">
            </head><body><a href="/old">Old</a></body></html>
        """,
        "https://archive.test/feed.xml": """
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry><link href="https://archive.test/new" rel="alternate"/></entry>
            </feed>
        """,
        "https://archive.test/sitemap.xml": """
            <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
              <url><loc>https://archive.test/new</loc></url>
              <url><loc>https://archive.test/old</loc></url>
              <url><loc>https://archive.test/older</loc></url>
            </urlset>
        """,
        "https://archive.test/new": "<html><head><title>New</title></head><body><article>" + "new writing " * 150 + "</article></body></html>",
        "https://archive.test/old": "<html><head><title>Old</title></head><body><article>" + "old writing " * 150 + "</article></body></html>",
        "https://archive.test/older": "<html><head><title>Older</title></head><body><article>" + "older writing " * 150 + "</article></body></html>",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in pages:
            content_type = "application/xml" if url.endswith(".xml") else "text/html"
            return httpx.Response(200, text=pages[url], headers={"content-type": content_type}, request=request)
        return httpx.Response(404, text="not found", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def client_for_bad_link_fixture() -> httpx.Client:
    pages = {
        "https://badlinks.test/": """
            <html><head><title>Bad Links</title></head><body>
            <article>""" + " ".join(["This essay has enough substantive prose to be indexed safely."] * 90) + """</article>
            <a href="http://I also strongly suspect this is prose, not a URL, and should never become a domain">Bad</a>
            <a href="javascript:void(0)">JS</a>
            <a href="mailto:test@example.com">Mail</a>
            <a href="https://valid.example.com/post">Valid</a>
            </body></html>
        """,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in pages:
            return httpx.Response(200, text=pages[url], headers={"content-type": "text/html"}, request=request)
        return httpx.Response(404, text="not found", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def client_for_first_candidate_failure_fixture() -> httpx.Client:
    pages = {
        "https://firstfail.test/": """
            <html><head>
            <link rel="alternate" type="application/atom+xml" href="/feed.xml">
            </head><body>Home</body></html>
        """,
        "https://firstfail.test/feed.xml": """
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry><link href="https://firstfail.test/missing" rel="alternate"/></entry>
              <entry><link href="https://firstfail.test/good" rel="alternate"/></entry>
            </feed>
        """,
        "https://firstfail.test/good": "<html><head><title>Good</title></head><body><article>" + "good writing " * 150 + "</article></body></html>",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url in pages:
            content_type = "application/xml" if url.endswith(".xml") else "text/html"
            return httpx.Response(200, text=pages[url], headers={"content-type": content_type}, request=request)
        return httpx.Response(404, text="not found", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_bfs_indexes_documents_links_and_discovers_external_source(session):
    source = get_or_create_source("https://a.test/", status="queued")
    job = Crawler(client_for_fixture()).crawl_source(source, max_pages=10, max_depth=1)

    assert job.status == "succeeded"
    assert job.pages_fetched == 3
    assert job.pages_failed >= 0
    assert session.query(Document).count() == 3
    assert session.query(Link).count() >= 4

    discovered = session.query(Source).filter_by(canonical_domain="b.test").one_or_none()
    assert discovered is not None
    assert discovered.status == "queued"

    youtube = session.query(Source).filter_by(canonical_domain="youtube.com").one_or_none()
    assert youtube is not None
    assert youtube.status == "queued"

    wikipedia = session.query(Source).filter_by(canonical_domain="en.wikipedia.org").one_or_none()
    assert wikipedia is not None
    assert wikipedia.status == "queued"

    titles = {doc.title for doc in session.query(Document).all()}
    assert "Deep" not in titles


def test_feed_does_not_prevent_sitemap_archive_crawl(session):
    source = get_or_create_source("https://archive.test/", status="queued")
    job = Crawler(client_for_feed_and_sitemap_fixture()).crawl_source(source, max_pages=10, max_depth=1)

    assert job.status == "succeeded"
    assert source.rss_url == "https://archive.test/feed.xml"
    assert source.sitemap_url == "https://archive.test/sitemap.xml"

    titles = {doc.title for doc in session.query(Document).all()}
    assert {"New", "Old", "Older"}.issubset(titles)


def test_ignored_source_is_skipped(session):
    source = get_or_create_source("https://www.youtube.com/",
        status="ignored",
    )
    job = Crawler(client_for_fixture()).crawl_source(source, max_pages=10, max_depth=1)

    assert job.status == "skipped"
    assert job.pages_fetched == 0
    assert source.status == "ignored"


def test_skip_existing_does_not_count_existing_pages_against_max_pages(session):
    source = get_or_create_source("https://a.test/", status="queued")
    first = Crawler(client_for_fixture()).crawl_source(source, max_pages=1, max_depth=1)
    source.status = "queued"

    second = Crawler(client_for_fixture()).crawl_source(
        source,
        max_pages=2,
        max_depth=1,
        skip_existing=True,
    )

    assert first.pages_fetched == 1
    assert second.pages_fetched == 2
    assert session.query(Document).count() == 3


def test_max_documents_stops_after_accepted_essays(session):
    source = get_or_create_source("https://a.test/", status="queued")
    job = Crawler(client_for_fixture()).crawl_source(source, max_pages=10, max_depth=1, max_documents=1)

    assert job.status == "succeeded"
    assert job.documents_indexed == 1
    assert session.query(Document).filter_by(document_type="essay").count() == 1


def test_bad_links_are_skipped_without_poisoning_crawl(session):
    source = get_or_create_source("https://badlinks.test/", status="queued")
    job = Crawler(client_for_bad_link_fixture()).crawl_source(source, max_pages=5, max_depth=1)

    assert job.status == "succeeded"
    assert job.pages_fetched == 1
    assert job.pages_failed == 0
    assert session.query(Document).count() == 1

    links = session.query(Link).all()
    assert len(links) == 1
    assert links[0].target_domain == "valid.example.com"


def test_first_candidate_failure_does_not_rollback_crawl_job(session):
    source = get_or_create_source("https://firstfail.test/", status="queued")
    job = Crawler(client_for_first_candidate_failure_fixture()).crawl_source(source, max_pages=5, max_depth=1)

    assert job.status == "succeeded"
    assert job.pages_failed == 1
    assert job.pages_fetched >= 1
    assert session.get(CrawlJob, job.id) is not None


def test_bfs_uses_active_pages_for_concurrent_processing(session, monkeypatch):
    source = get_or_create_source("https://a.test/", status="queued")
    active = 0
    max_active = 0

    async def fake_process_page(self, url: str):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        path = httpx.URL(url).path
        links = []
        if path == "/":
            links = [
                ExtractedLink(url="https://a.test/one", anchor_text="One", context="One"),
                ExtractedLink(url="https://a.test/two", anchor_text="Two", context="Two"),
            ]
        fetched = FetchResult(url=url, final_url=url, content_type="text/html", text="<html></html>")
        extracted = ExtractedPage(
            title=path or "/",
            author=None,
            published_at=None,
            text="body",
            summary="summary",
            topics=["test"],
            document_type="essay",
            category_slug="software",
            links=links,
        )
        return PagePipelineResult(
            requested_url=url,
            fetched=fetched,
            extracted=extracted,
            content_hash=url,
            embedding="[1.0]",
        )

    monkeypatch.setattr(Crawler, "_process_page_async", fake_process_page)

    job = Crawler(client_for_fixture()).crawl_source(source, max_pages=3, max_depth=1, active_pages=2)

    assert job.status == "succeeded"
    assert job.pages_fetched == 3
    assert max_active == 2
