from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.parse import urlunparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from iris.config import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES, MAX_HTML_BYTES, REQUEST_TIMEOUT_SECONDS, USER_AGENT
from iris.embedding import dumps_embedding, embed_text
from iris.extract import extract_page
from iris.models import CrawlJob, Document, Source
from iris.repository import get_or_create_source, upsert_document, upsert_link
from iris.source_classifier import classify_source_homepage
from iris.url_utils import content_hash, domain_for_url, is_probably_static, is_valid_http_url, normalize_url, same_domain


logger = logging.getLogger("iris.crawler")


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    content_type: str
    text: str


class Crawler:
    def __init__(self, session: Session, client: httpx.Client | None = None):
        self.session = session
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers={"User-Agent": USER_AGENT},
        )

    def crawl_source(
        self,
        source: Source,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_depth: int = DEFAULT_MAX_DEPTH,
        *,
        skip_existing: bool = False,
        max_documents: int | None = None,
    ) -> CrawlJob:
        job = CrawlJob(source_id=source.id, status="running")
        self.session.add(job)
        self.session.flush()
        if source.status == "ignored":
            job.status = "skipped"
            job.error = f"source is ignored ({source.source_type})"
            job.finished_at = datetime.now(timezone.utc)
            logger.info("Skipping ignored source %s (%s)", source.canonical_domain, source.source_type)
            self.session.flush()
            return job
        source.status = "crawling"
        source.last_checked_at = datetime.now(timezone.utc)
        self.session.flush()
        self.session.commit()
        try:
            logger.info(
                "crawl start domain=%s max_pages=%s max_depth=%s max_documents=%s skip_existing=%s",
                source.canonical_domain,
                max_pages,
                max_depth,
                max_documents or "none",
                skip_existing,
            )
            homepage_result = self._fetch(source.homepage_url)
            classification = classify_source_homepage(homepage_result.final_url, homepage_result.text)
            source.source_type = classification.source_type
            source.quality_score = classification.confidence
            source.description = classification.reason
            if classification.status == "ignored":
                source.status = "ignored"
                job.status = "skipped"
                job.error = f"source classifier rejected crawl: {classification.reason}"
                logger.info(
                    "source rejected domain=%s type=%s reason=%s",
                    source.canonical_domain,
                    classification.source_type,
                    classification.reason,
                )
                return job
            confidence = f"{classification.confidence:.2f}" if classification.confidence is not None else "unknown"
            logger.info(
                "source accepted domain=%s type=%s confidence=%s",
                source.canonical_domain,
                classification.source_type,
                confidence,
            )
            candidates = self._candidate_urls(source, homepage_result)
            self.session.flush()
            self.session.commit()
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
                for url in urls:
                    if self._limits_reached(job, max_pages=max_pages, max_documents=max_documents):
                        break
                    job.pages_queued += 1
                    self._crawl_one(source, url, job, skip_existing=skip_existing)
                if not self._limits_reached(job, max_pages=max_pages, max_documents=max_documents):
                    self._bfs(
                        source,
                        job,
                        max_pages=max_pages,
                        max_depth=max_depth,
                        max_documents=max_documents,
                        skip_existing=skip_existing,
                        initial_visited={normalize_url(url) for url in urls},
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
                exhausted = self._bfs(
                    source,
                    job,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    max_documents=max_documents,
                    skip_existing=skip_existing,
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
            source.status = "indexed"
            job.status = "succeeded"
        except Exception as exc:
            logger.exception("Crawl failed for %s", source.canonical_domain)
            source.status = "failed"
            job.status = "failed"
            job.error = str(exc)
        finally:
            job.finished_at = datetime.now(timezone.utc)
            self.session.flush()
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
            if not same_domain(normalized, source.homepage_url):
                continue
            path = urlparse(normalized).path
            if path in {"", "/"}:
                continue
            deduped.append(normalized)
            seen.add(normalized)
        return deduped

    def _bfs(
        self,
        source: Source,
        job: CrawlJob,
        *,
        max_pages: int,
        max_depth: int,
        max_documents: int | None = None,
        skip_existing: bool = False,
        initial_visited: set[str] | None = None,
    ) -> bool:
        queue: deque[tuple[str, int]] = deque([(source.homepage_url, 0)])
        queued = {normalize_url(source.homepage_url)}
        visited: set[str] = set(initial_visited or set())
        while queue and not self._limits_reached(job, max_pages=max_pages, max_documents=max_documents):
            url, depth = queue.popleft()
            normalized = normalize_url(url)
            if normalized in visited or is_probably_static(normalized):
                continue
            visited.add(normalized)
            document = self._crawl_one(source, normalized, job, skip_existing=skip_existing)
            if depth >= max_depth or not document:
                continue
            for link in document.outgoing_links:
                target = normalize_url(link.normalized_target_url)
                if link.link_type != "internal" or target in queued or is_probably_static(target):
                    continue
                queue.append((target, depth + 1))
                queued.add(target)
                job.pages_queued += 1
        return not queue

    def _crawl_one(self, source: Source, url: str, job: CrawlJob, *, skip_existing: bool = False) -> Document | None:
        job_id = job.id
        try:
            normalized = normalize_url(url)
            if not is_valid_http_url(normalized):
                logger.debug("Skipping invalid URL: %s", url)
                return None
            if skip_existing:
                existing = self._existing_document_for_url(normalized)
                if existing and existing.crawl_status == "fetched":
                    logger.debug("Skipping already fetched URL: %s", normalized)
                    return existing
            fetched = self._fetch(url)
            if "html" not in fetched.content_type and not fetched.text.lstrip().startswith("<"):
                return None
            extracted = extract_page(fetched.text, fetched.final_url)
            text_hash = content_hash(extracted.text)
            embedding = dumps_embedding(embed_text(f"{extracted.title or ''}\n{extracted.summary}\n{extracted.text[:4000]}"))
            document = upsert_document(
                self.session,
                source=source,
                url=fetched.url,
                final_url=fetched.final_url,
                document_type=extracted.document_type,
                crawl_status="fetched",
                title=extracted.title,
                author=extracted.author,
                published_at=extracted.published_at,
                extracted_text=extracted.text,
                summary=extracted.summary,
                topics=extracted.topics,
                embedding=embedding,
                quality_score=extracted.quality_score,
                content_hash=text_hash,
            )
            job.pages_fetched += 1
            if extracted.document_type == "essay":
                job.documents_indexed += 1
                logger.info(
                    "doc accepted domain=%s docs=%s fetched=%s title=%s",
                    source.canonical_domain,
                    job.documents_indexed,
                    job.pages_fetched,
                    _short_log_text(extracted.title or fetched.final_url),
                )
            elif job.pages_fetched % 25 == 0:
                logger.info(
                    "crawl progress domain=%s fetched=%s docs=%s links=%s",
                    source.canonical_domain,
                    job.pages_fetched,
                    job.documents_indexed,
                    job.links_seen,
                )
            for extracted_link in extracted.links:
                normalized_target = normalize_url(extracted_link.url, fetched.final_url)
                if not is_valid_http_url(normalized_target) or is_probably_static(normalized_target):
                    continue
                link = upsert_link(
                    self.session,
                    source_document=document,
                    target_url=extracted_link.url,
                    anchor_text=extracted_link.anchor_text,
                    context=extracted_link.context,
                )
                job.links_seen += 1
                if link.link_type == "external" and link.target_domain:
                    before = self.session.execute(select(Source).where(Source.canonical_domain == link.target_domain)).scalar_one_or_none()
                    discovered = get_or_create_source(
                        self.session,
                        normalized_target,
                        status="queued",
                        discovered_from_source_id=source.id,
                    )
                    link.target_source_id = discovered.id
                    if before is None:
                        job.sources_discovered += 1
            self._resolve_links_for_document(document)
            self.session.flush()
            self.session.commit()
            return document
        except Exception as exc:
            logger.warning("Failed to crawl %s: %s", url, exc)
            self.session.rollback()
            persisted_job = self.session.get(CrawlJob, job_id)
            if persisted_job:
                persisted_job.pages_failed += 1
                self.session.flush()
                self.session.commit()
            return None

    def _limits_reached(self, job: CrawlJob, *, max_pages: int, max_documents: int | None) -> bool:
        if job.pages_fetched >= max_pages:
            return True
        return bool(max_documents and job.documents_indexed >= max_documents)

    def _existing_document_for_url(self, normalized_url: str) -> Document | None:
        candidates = {normalized_url, _alternate_http_scheme(normalized_url)}
        return self.session.execute(select(Document).where(Document.final_url.in_(candidates))).scalar_one_or_none()

    def _resolve_links_for_document(self, document: Document) -> None:
        for link in document.outgoing_links:
            target_document = self.session.execute(
                select(Document).where(Document.final_url == link.normalized_target_url)
            ).scalar_one_or_none()
            if target_document:
                link.target_document_id = target_document.id
                link.target_source_id = target_document.source_id
            elif link.target_domain:
                target_source = self.session.execute(
                    select(Source).where(Source.canonical_domain == link.target_domain)
                ).scalar_one_or_none()
                if target_source:
                    link.target_source_id = target_source.id


def crawl_source(
    session: Session,
    source: Source,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_depth: int = DEFAULT_MAX_DEPTH,
    *,
    skip_existing: bool = False,
    max_documents: int | None = None,
) -> CrawlJob:
    return Crawler(session).crawl_source(
        source,
        max_pages=max_pages,
        max_depth=max_depth,
        skip_existing=skip_existing,
        max_documents=max_documents,
    )


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
