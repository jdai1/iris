from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.parse import urlunparse

import httpx
from bs4 import BeautifulSoup

from iris.dao import db
from iris.dao import crawler as crawler_dao
from iris.dao.documents import upsert_document
from iris.dao.categories import assign_category, get_or_create_category
from iris.dao.links import upsert_link
from iris.dao.sources import get_or_create_source
from iris.services.common.config import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, MAX_HTML_BYTES, REQUEST_TIMEOUT_SECONDS, USER_AGENT
from iris.services.ingestion.embedding import document_embedding_text, dumps_embedding, embed_text_async
from iris.services.ingestion.extract import extract_page_async
from iris.models import CrawlJob, Document, Source
from iris.schemas.enums import CrawlJobStatus, CrawlStatus, DocumentType, LinkType, SourceStatus
from iris.schemas.ingestion import ExtractedPage, FetchResult
from iris.services.ingestion.source_classifier import classify_source_homepage
from iris.services.retrieval.source_profiles import generate_source_profile
from iris.services.common.url_utils import content_hash, is_probably_static, is_valid_http_url, normalize_url, same_domain


logger = logging.getLogger("iris.crawler")


@dataclass(frozen=True)
class PagePipelineResult:
    """Detached result from the async fetch/extract/embed pipeline."""

    requested_url: str
    fetched: FetchResult | None
    extracted: ExtractedPage | None
    content_hash: str | None
    embedding: str | None
    error: str | None = None


class Crawler:
    def __init__(self, client: httpx.Client | None = None):
        self._uses_injected_client = client is not None
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )
        self.async_client: httpx.AsyncClient | None = None

    def crawl_source(
        self,
        source: Source,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_depth: int = DEFAULT_MAX_DEPTH,
        *,
        skip_existing: bool = False,
        max_documents: int | None = None,
        active_pages: int = 4,
    ) -> CrawlJob:
        """Crawl one source with bounded in-source async page concurrency."""
        return asyncio.run(
            self._crawl_source_async(
                source,
                max_pages=max_pages,
                max_depth=max_depth,
                skip_existing=skip_existing,
                max_documents=max_documents,
                active_pages=active_pages,
            )
        )

    async def _crawl_source_async(
        self,
        source: Source,
        max_pages: int,
        max_depth: int,
        *,
        skip_existing: bool,
        max_documents: int | None,
        active_pages: int,
    ) -> CrawlJob:
        job = crawler_dao.create_crawl_job(source)
        if source.status == SourceStatus.IGNORED.value:
            crawler_dao.skip_crawl_job(job, "source is ignored")
            logger.info("Skipping ignored source %s", source.canonical_domain)
            return job
        crawler_dao.mark_source_crawling(source)
        db.commit()
        try:
            logger.info(
                "crawl start domain=%s max_pages=%s max_depth=%s max_documents=%s skip_existing=%s active_pages=%s",
                source.canonical_domain,
                max_pages,
                max_depth,
                max_documents or "none",
                skip_existing,
                max(1, active_pages),
            )
            homepage_result = self._fetch(source.url)
            classification = classify_source_homepage(homepage_result.final_url, homepage_result.text)
            source.description = classification.reason
            if classification.status == SourceStatus.IGNORED.value:
                source.status = SourceStatus.IGNORED.value
                job.status = CrawlJobStatus.SKIPPED.value
                job.error = f"source classifier rejected crawl: {classification.reason}"
                logger.info(
                    "source rejected domain=%s reason=%s",
                    source.canonical_domain,
                    classification.reason,
                )
                return job
            logger.info(
                "source accepted domain=%s",
                source.canonical_domain,
            )
            candidates = await self._candidate_urls_async(source, homepage_result)
            db.flush()
            db.commit()
            if candidates:
                logger.info("crawl candidates domain=%s count=%s", source.canonical_domain, len(candidates))
                urls = candidates if skip_existing else candidates[:max_pages]
                if len(candidates) > max_pages:
                    logger.info(
                        "crawl cap domain=%s max_pages=%s candidates=%s",
                        source.canonical_domain,
                        max_pages,
                        len(candidates),
                    )
                visited = await self._crawl_candidate_urls_async(
                    source,
                    job,
                    urls,
                    max_pages=max_pages,
                    max_documents=max_documents,
                    skip_existing=skip_existing,
                    active_pages=active_pages,
                )
                if not self._limits_reached(job, max_pages=max_pages, max_documents=max_documents):
                    await self._bfs_async(
                        source,
                        job,
                        max_pages=max_pages,
                        max_depth=max_depth,
                        max_documents=max_documents,
                        skip_existing=skip_existing,
                        initial_visited=visited,
                        active_pages=active_pages,
                    )
                elif max_documents and job.documents_indexed >= max_documents:
                    logger.info(
                        "crawl stop domain=%s reason=max_documents limit=%s",
                        source.canonical_domain,
                        max_documents,
                    )
                elif len(candidates) > max_pages:
                    logger.info("crawl stop domain=%s reason=max_pages limit=%s", source.canonical_domain, max_pages)
                else:
                    logger.info("crawl stop domain=%s reason=candidates_exhausted", source.canonical_domain)
            else:
                logger.info("crawl candidates domain=%s count=0 mode=bfs", source.canonical_domain)
                exhausted = await self._bfs_async(
                    source,
                    job,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    max_documents=max_documents,
                    skip_existing=skip_existing,
                    active_pages=active_pages,
                )
                if exhausted:
                    logger.info("crawl stop domain=%s reason=queue_exhausted", source.canonical_domain)
                elif max_documents and job.documents_indexed >= max_documents:
                    logger.info(
                        "crawl stop domain=%s reason=max_documents limit=%s",
                        source.canonical_domain,
                        max_documents,
                    )
                else:
                    logger.info("crawl stop domain=%s reason=max_pages limit=%s", source.canonical_domain, max_pages)
            source.status = SourceStatus.INDEXED.value
            job.status = CrawlJobStatus.SUCCEEDED.value
        except Exception as exc:
            logger.exception("Crawl failed for %s", source.canonical_domain)
            source.status = SourceStatus.FAILED.value
            job.status = CrawlJobStatus.FAILED.value
            job.error = str(exc)
        finally:
            crawler_dao.finish_crawl_job(job)
            if self.async_client:
                await self.async_client.aclose()
                self.async_client = None
        if job.status == CrawlJobStatus.SUCCEEDED.value and source.status == SourceStatus.INDEXED.value:
            try:
                generate_source_profile(source)
            except Exception as exc:
                logger.warning("Source profile generation failed for %s: %s", source.canonical_domain, exc)
        return job

    def _fetch(self, url: str) -> FetchResult:
        normalized = normalize_url(url)
        response = self.client.get(normalized)
        response.raise_for_status()
        content = response.content[:MAX_HTML_BYTES]
        text = content.decode(response.encoding or "utf-8", errors="replace")
        return FetchResult(
            url=normalized,
            final_url=normalize_url(str(response.url)),
            content_type=response.headers.get("content-type", ""),
            text=text,
        )

    async def _fetch_async(self, url: str) -> FetchResult:
        if self._uses_injected_client:
            return await asyncio.to_thread(self._fetch, url)
        if self.async_client is None:
            self.async_client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=REQUEST_TIMEOUT_SECONDS,
                headers={"User-Agent": USER_AGENT},
            )
        normalized = normalize_url(url)
        response = await self.async_client.get(normalized)
        response.raise_for_status()
        content = response.content[:MAX_HTML_BYTES]
        text = content.decode(response.encoding or "utf-8", errors="replace")
        return FetchResult(
            url=normalized,
            final_url=normalize_url(str(response.url)),
            content_type=response.headers.get("content-type", ""),
            text=text,
        )

    def _candidate_urls(self, source: Source, homepage_result: FetchResult) -> list[str]:
        candidates: list[str] = []
        feed_urls = self._discover_feed_urls(homepage_result.text, homepage_result.final_url)
        for feed_url in feed_urls:
            try:
                feed_result = self._fetch(feed_url)
                urls = self._parse_feed(feed_result.text, feed_result.final_url)
                if urls:
                    source.rss_url = feed_result.final_url
                    candidates.extend(urls)
            except Exception:
                logger.debug("Feed candidate failed: %s", feed_url, exc_info=True)

        sitemap_urls = self._discover_sitemap_urls(homepage_result.text, homepage_result.final_url)
        for sitemap_url in sitemap_urls:
            try:
                sitemap_result = self._fetch(sitemap_url)
                urls = self._parse_sitemap(sitemap_result.text, sitemap_result.final_url)
                if urls:
                    source.sitemap_url = sitemap_result.final_url
                    candidates.extend(urls)
            except Exception:
                logger.debug("Sitemap candidate failed: %s", sitemap_url, exc_info=True)

        return self._dedupe_candidate_urls(source, candidates)

    async def _candidate_urls_async(self, source: Source, homepage_result: FetchResult) -> list[str]:
        candidates: list[str] = []
        feed_urls = self._discover_feed_urls(homepage_result.text, homepage_result.final_url)
        for feed_url in feed_urls:
            try:
                feed_result = await self._fetch_async(feed_url)
                urls = self._parse_feed(feed_result.text, feed_result.final_url)
                if urls:
                    source.rss_url = feed_result.final_url
                    candidates.extend(urls)
            except Exception:
                logger.debug("Feed candidate failed: %s", feed_url, exc_info=True)

        sitemap_urls = self._discover_sitemap_urls(homepage_result.text, homepage_result.final_url)
        for sitemap_url in sitemap_urls:
            try:
                sitemap_result = await self._fetch_async(sitemap_url)
                urls = await self._parse_sitemap_async(sitemap_result.text, sitemap_result.final_url)
                if urls:
                    source.sitemap_url = sitemap_result.final_url
                    candidates.extend(urls)
            except Exception:
                logger.debug("Sitemap candidate failed: %s", sitemap_url, exc_info=True)

        return self._dedupe_candidate_urls(source, candidates)

    def _discover_feed_urls(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        for tag in soup.find_all("link", rel=True, href=True):
            rel = " ".join(tag.get("rel", [])).lower()
            content_type = str(tag.get("type", "")).lower()
            if "alternate" in rel and ("rss" in content_type or "atom" in content_type or "xml" in content_type):
                urls.append(normalize_url(str(tag["href"]), base_url))
        for path in ("/feed.xml", "/rss.xml", "/atom.xml", "/feed", "/rss"):
            urls.append(normalize_url(urljoin(base_url, path)))
        return list(dict.fromkeys(urls))

    async def _parse_sitemap_async(self, xml_text: str, base_url: str) -> list[str]:
        root = ET.fromstring(xml_text.encode("utf-8"))
        urls: list[str] = []
        for loc in root.findall(".//{*}url/{*}loc"):
            if loc.text:
                urls.append(normalize_url(loc.text, base_url))
        for loc in root.findall(".//{*}sitemap/{*}loc"):
            if not loc.text:
                continue
            try:
                nested = await self._fetch_async(loc.text)
                urls.extend(await self._parse_sitemap_async(nested.text, nested.final_url))
            except Exception:
                logger.debug("Nested sitemap failed: %s", loc.text, exc_info=True)
        return list(dict.fromkeys(urls))

    def _discover_sitemap_urls(self, html: str, base_url: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        urls: list[str] = []
        for tag in soup.find_all("link", href=True):
            rel = " ".join(tag.get("rel", [])).lower()
            href = str(tag["href"])
            if "sitemap" in rel or href.endswith("sitemap.xml"):
                urls.append(normalize_url(href, base_url))
        urls.append(normalize_url(urljoin(base_url, "/sitemap.xml")))
        return list(dict.fromkeys(urls))

    def _parse_feed(self, xml_text: str, base_url: str) -> list[str]:
        root = ET.fromstring(xml_text.encode("utf-8"))
        urls: list[str] = []
        for item in root.findall(".//item"):
            link = item.findtext("link")
            if link:
                urls.append(normalize_url(link, base_url))
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            for link in entry.findall("atom:link", ns):
                href = link.attrib.get("href")
                rel = link.attrib.get("rel", "alternate")
                if href and rel == "alternate":
                    urls.append(normalize_url(href, base_url))
        return list(dict.fromkeys(urls))

    def _parse_sitemap(self, xml_text: str, base_url: str) -> list[str]:
        root = ET.fromstring(xml_text.encode("utf-8"))
        urls: list[str] = []
        for loc in root.findall(".//{*}url/{*}loc"):
            if loc.text:
                urls.append(normalize_url(loc.text, base_url))
        for loc in root.findall(".//{*}sitemap/{*}loc"):
            if not loc.text:
                continue
            try:
                nested = self._fetch(loc.text)
                urls.extend(self._parse_sitemap(nested.text, nested.final_url))
            except Exception:
                logger.debug("Nested sitemap failed: %s", loc.text, exc_info=True)
        return list(dict.fromkeys(urls))

    def _dedupe_candidate_urls(self, source: Source, urls: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for url in urls:
            normalized = normalize_url(url)
            if normalized in seen or is_probably_static(normalized):
                continue
            if not same_domain(normalized, source.url):
                continue
            path = urlparse(normalized).path
            if path in {"", "/"}:
                continue
            deduped.append(normalized)
            seen.add(normalized)
        return deduped

    async def _crawl_candidate_urls_async(
        self,
        source: Source,
        job: CrawlJob,
        urls: list[str],
        *,
        max_pages: int,
        max_documents: int | None,
        skip_existing: bool,
        active_pages: int,
    ) -> set[str]:
        visited: set[str] = set()
        pending: set[asyncio.Task[PagePipelineResult]] = set()
        url_index = 0
        active_pages = max(1, active_pages)

        def effective_active_limit() -> int:
            if not max_documents:
                return active_pages
            remaining_documents = max_documents - job.documents_indexed
            return max(0, min(active_pages, remaining_documents))

        def schedule_available() -> None:
            nonlocal url_index
            while (
                url_index < len(urls)
                and len(pending) < effective_active_limit()
                and not self._limits_reached(job, max_pages=max_pages, max_documents=max_documents)
            ):
                url = urls[url_index]
                url_index += 1
                normalized = normalize_url(url)
                if normalized in visited or is_probably_static(normalized):
                    continue
                visited.add(normalized)
                if skip_existing and self._existing_document_for_url(normalized):
                    logger.debug("Skipping already fetched URL: %s", normalized)
                    continue
                job.pages_queued += 1
                pending.add(asyncio.create_task(self._process_page_async(normalized)))

        schedule_available()
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                self._persist_page_result(source, job, task.result())
            schedule_available()
        return visited

    async def _bfs_async(
        self,
        source: Source,
        job: CrawlJob,
        *,
        max_pages: int,
        max_depth: int,
        max_documents: int | None = None,
        skip_existing: bool = False,
        initial_visited: set[str] | None = None,
        active_pages: int = 4,
    ) -> bool:
        queue: asyncio.Queue[tuple[str, int]] = asyncio.Queue()
        queue.put_nowait((source.url, 0))
        queued = {normalize_url(source.url)}
        visited: set[str] = set(initial_visited or set())
        pending: dict[asyncio.Task[PagePipelineResult], int] = {}
        active_pages = max(1, active_pages)

        def effective_active_limit() -> int:
            if not max_documents:
                return active_pages
            remaining_documents = max_documents - job.documents_indexed
            return max(0, min(active_pages, remaining_documents))

        def expand_document(document: Document, depth: int) -> None:
            if depth >= max_depth or self._limits_reached(job, max_pages=max_pages, max_documents=max_documents):
                return
            for link in document.outgoing_links:
                target = normalize_url(link.target_url)
                if link.link_type != LinkType.INTERNAL.value or target in queued or is_probably_static(target):
                    continue
                queue.put_nowait((target, depth + 1))
                queued.add(target)
                job.pages_queued += 1

        def schedule_available() -> None:
            while (
                not queue.empty()
                and len(pending) < effective_active_limit()
                and not self._limits_reached(job, max_pages=max_pages, max_documents=max_documents)
            ):
                url, depth = queue.get_nowait()
                normalized = normalize_url(url)
                if normalized in visited or is_probably_static(normalized):
                    continue
                visited.add(normalized)
                if skip_existing:
                    existing = self._existing_document_for_url(normalized)
                    if existing and existing.crawl_status == CrawlStatus.FETCHED.value:
                        logger.debug("Skipping already fetched URL: %s", normalized)
                        expand_document(existing, depth)
                        continue
                pending[asyncio.create_task(self._process_page_async(normalized))] = depth

        schedule_available()
        while pending:
            done, _ = await asyncio.wait(set(pending), return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                depth = pending.pop(task)
                document = self._persist_page_result(source, job, task.result())
                if document:
                    expand_document(document, depth)
            schedule_available()
        return queue.empty()

    async def _process_page_async(self, url: str) -> PagePipelineResult:
        try:
            normalized = normalize_url(url)
            if not is_valid_http_url(normalized):
                logger.debug("Skipping invalid URL: %s", url)
                return PagePipelineResult(url, None, None, None, None)
            fetched = await self._fetch_async(url)
            if "html" not in fetched.content_type and not fetched.text.lstrip().startswith("<"):
                return PagePipelineResult(url, fetched, None, None, None)
            extracted = await extract_page_async(fetched.text, fetched.final_url)
            text_hash = content_hash(extracted.text)
            embedding = dumps_embedding(
                await embed_text_async(
                    document_embedding_text(
                        title=extracted.title,
                        summary=extracted.summary,
                        topics=extracted.topics,
                        extracted_text=extracted.text,
                    )
                )
            )
            return PagePipelineResult(url, fetched, extracted, text_hash, embedding)
        except Exception as exc:
            return PagePipelineResult(url, None, None, None, None, error=str(exc))

    def _persist_page_result(
        self,
        source: Source,
        job: CrawlJob,
        result: PagePipelineResult,
    ) -> Document | None:
        try:
            if result.error:
                raise RuntimeError(result.error)
            if not result.fetched or not result.extracted:
                return None
            fetched = result.fetched
            extracted = result.extracted
            document = upsert_document(
                source=source,
                crawl_job_id=job.id,
                url=fetched.final_url,
                document_type=extracted.document_type,
                crawl_status=CrawlStatus.FETCHED.value,
                title=extracted.title,
                author=extracted.author,
                published_at=extracted.published_at,
                extracted_text=extracted.text,
                summary=extracted.summary,
                topics=extracted.topics,
                embedding=result.embedding,
                content_hash=result.content_hash,
            )
            if extracted.category_slug:
                assign_category(document, get_or_create_category(extracted.category_slug), assigned_by="llm")
            job.pages_fetched += 1
            if extracted.document_type == DocumentType.ESSAY.value:
                job.documents_indexed += 1
                logger.info(
                    "doc accepted domain=%s docs=%s fetched=%s title=%s",
                    source.canonical_domain,
                    job.documents_indexed,
                    job.pages_fetched,
                    _short_log_text(extracted.title or fetched.final_url),
                )
                print(
                    f"doc done domain={source.canonical_domain} "
                    f"docs={job.documents_indexed} fetched={job.pages_fetched} "
                    f"type={extracted.document_type} title={_short_log_text(extracted.title or fetched.final_url)}",
                    flush=True,
                )
            elif job.pages_fetched % 25 == 0:
                logger.info(
                    "crawl progress domain=%s fetched=%s docs=%s links=%s",
                    source.canonical_domain,
                    job.pages_fetched,
                    job.documents_indexed,
                    job.links_seen,
                )
                print(
                    f"doc done domain={source.canonical_domain} "
                    f"docs={job.documents_indexed} fetched={job.pages_fetched} "
                    f"type={extracted.document_type} title={_short_log_text(extracted.title or fetched.final_url)}",
                    flush=True,
                )
            for extracted_link in extracted.links:
                normalized_target = normalize_url(extracted_link.url, fetched.final_url)
                if not is_valid_http_url(normalized_target) or is_probably_static(normalized_target):
                    continue
                link = upsert_link(
                    source_document=document,
                    target_url=extracted_link.url,
                    anchor_text=extracted_link.anchor_text,
                    context=extracted_link.context,
                )
                job.links_seen += 1
                if link.link_type == LinkType.EXTERNAL.value and link.target_domain:
                    before = crawler_dao.get_source_by_domain(link.target_domain)
                    discovered = get_or_create_source(
                        normalized_target,
                        status=SourceStatus.QUEUED.value,
                        discovered_from_source_id=source.id,
                    )
                    link.target_source_id = discovered.id
                    if before is None:
                        job.sources_discovered += 1
            crawler_dao.set_document_link_targets(document)
            db.flush()
            db.commit()
            return document
        except Exception as exc:
            logger.warning("Failed to crawl %s: %s", result.requested_url, exc)
            db.rollback()
            persisted_job = crawler_dao.get_crawl_job(job.id)
            if persisted_job:
                persisted_job.pages_failed += 1
                db.flush()
                db.commit()
                print(
                    f"doc failed domain={source.canonical_domain} "
                    f"failed={persisted_job.pages_failed} url={_short_log_text(result.requested_url)} "
                    f"error={_short_log_text(str(exc))}",
                    flush=True,
                )
            return None

    def _limits_reached(self, job: CrawlJob, *, max_pages: int, max_documents: int | None) -> bool:
        if job.pages_fetched >= max_pages:
            return True
        return bool(max_documents and job.documents_indexed >= max_documents)

    def _existing_document_for_url(self, normalized_url: str) -> Document | None:
        candidates = {normalized_url, _alternate_http_scheme(normalized_url)}
        return crawler_dao.get_document_by_urls(candidates)


def _alternate_http_scheme(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "http":
        return urlunparse(("https", parsed.netloc, parsed.path, "", parsed.query, ""))
    if parsed.scheme == "https":
        return urlunparse(("http", parsed.netloc, parsed.path, "", parsed.query, ""))
    return url


def _short_log_text(value: str, max_chars: int = 96) -> str:
    compact = " ".join(value.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3] + "..."
