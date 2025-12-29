import asyncio
import uuid

import aiohttp
import app.db as db
from app.constants import (
    MAX_INTERNAL_LINKS_Q_SIZE,
    TOO_MANY_INTERNAL_LINKS_REASON,
    URL_DEPTH_TOLERANCE,
    URL_REPETITION_TOLERANCE,
)
from app.dao.domain import (
    create_domains_batch,
    get_domains_by_urls,
    get_or_create_domain_by_url,
)
from app.dao.entry import create_entries_batch
from sqlalchemy import select
from app.dao.link import create_links_batch, get_links_by_urls
from app.dao.mappings import (
    create_domain_mappings_batch,
    create_link_mappings_batch,
)
from app.enums.core import DomainStatus
from app.exceptions import (
    FatalException,
    SkipCrawlingDomainException,
    TooManyInternalLinksException,
)
from app.models.models import Domain, Entry, Link
from app.schemas.crawl import (
    DomainCreateParams,
    DomainMappingCreateParams,
    EntryCreateParams,
    LinkCreateParams,
    LinkMappingCreateParams,
    PageCrawlResult,
)
from app.schemas.llm import EntryWithEmbedding
from app.services.embedding_service import generate_embedding
from app.services.llm_services import classify_domain, parse_entry
from app.utils.date_utils import parse_date
from app.utils.scrape_utils import crawl_url, extract_text_from_html
from app.utils.url_utils import (
    get_domain,
    get_url_depth,
    get_url_path_count,
    is_from_same_domain_or_subdomain,
    is_id_or_static_resource,
    sanitize_url,
)
from app.utils.logger import scraper_logger as logger


def _is_valid_internal_link(domain_url: str, url: str) -> bool:
    """Check if URL is a valid internal link to crawl."""
    path_count = get_url_path_count(url)
    return (
        not is_id_or_static_resource(url)
        and is_from_same_domain_or_subdomain(url, domain_url)
        and get_url_depth(url) < URL_DEPTH_TOLERANCE
        and (max(path_count.values()) if path_count else 0) < URL_REPETITION_TOLERANCE
    )


async def _crawl_pages(
    http_session: aiohttp.ClientSession,
    start_url: str,
    domain_url: str,
    max_depth: int = 10,
    batch_size: int = 50,
) -> dict[str, PageCrawlResult]:
    """
    BFS traversal to collect PageCrawlResult objects from domain.

    Returns:
        Dict mapping url -> PageCrawlResult
    """
    logger.info(
        "Starting BFS crawl",
        extra={
            "start_url": start_url,
            "domain": domain_url,
            "max_depth": max_depth,
            "batch_size": batch_size,
        },
    )

    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(sanitize_url(start_url), 0)]  # (url, depth)
    url_to_crawl_result: dict[str, PageCrawlResult] = {}
    batch_num = 0
    total_errors = 0

    while queue:
        batch: list[tuple[str, int]] = []

        # Collect batch
        while queue and len(batch) < batch_size:
            url, depth = queue.pop(0)
            if url in visited or depth >= max_depth:
                if url in visited:
                    logger.debug(f"SKIP (already visited): {url}")
                elif depth >= max_depth:
                    logger.debug(f"SKIP (max depth reached): {url} (depth={depth})")
                continue
            visited.add(url)
            batch.append((url, depth))

        if not batch:
            break

        batch_num += 1
        logger.info(
            f"Batch {batch_num}: Fetching {len(batch)} URLs (queue: {len(queue)}, crawled: {len(url_to_crawl_result)})"
        )
        for url, depth in batch:
            logger.debug(f"[depth={depth}] {url}")

        # Fetch batch in parallel
        tasks = [crawl_url(http_session, url) for url, _ in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        batch_success = 0
        batch_errors = 0
        new_links_added = 0

        for (url, depth), result in zip(batch, results):
            if isinstance(result, Exception):
                batch_errors += 1
                total_errors += 1
                logger.error(
                    f"ERROR [{url}]: {type(result).__name__}: {str(result)[:80]}"
                )
                continue

            crawl_result = result
            final_url = crawl_result.redirected_url

            # Handle redirects
            if final_url != url:
                final_url = sanitize_url(final_url)
                logger.debug(f"REDIRECT [{url}] → [{final_url}]")
                if not _is_valid_internal_link(domain_url, final_url):
                    logger.debug("SKIP: Redirect target not valid internal link")
                    continue
                if final_url in visited:
                    logger.debug("SKIP: Redirect target already visited")
                    continue

            # Store crawl result
            url_to_crawl_result[final_url] = crawl_result  # type: ignore
            batch_success += 1

            # Extract internal links for queue
            internal_links = crawl_result.links.internal
            external_links = crawl_result.links.external
            logger.debug(
                f"Processing {len(internal_links)} internal links from {final_url}..."
            )
            for link in internal_links:
                link = sanitize_url(link)
                if link in visited:
                    logger.debug(f"SKIP (visited): {link}")
                    continue
                if not _is_valid_internal_link(domain_url, link):
                    logger.debug(f"SKIP (invalid): {link}")
                    continue

                # Check if queue exceeds maximum size
                if len(queue) >= MAX_INTERNAL_LINKS_Q_SIZE:
                    raise TooManyInternalLinksException(
                        f"Queue size ({len(queue)}) exceeds maximum ({MAX_INTERNAL_LINKS_Q_SIZE})"
                    )

                queue.append((link, depth + 1))
                new_links_added += 1
                logger.debug(f"QUEUED (depth={depth + 1}): {link}")

            logger.debug(
                f"[{final_url}] - {len(internal_links)} internal, {len(external_links)} external links"
            )

        logger.info(
            f"Batch {batch_num} complete: {batch_success} OK, {batch_errors} errors, +{new_links_added} new links queued"
        )

    logger.info(
        "Crawl complete",
        extra={
            "total_pages": len(url_to_crawl_result),
            "total_errors": total_errors,
            "total_batches": batch_num,
        },
    )

    return url_to_crawl_result


async def _extract_data(
    url_to_crawl_result: dict[str, PageCrawlResult], batch_size: int = 10
) -> dict[str, EntryWithEmbedding]:
    """
    Process all HTML via LLM to extract entries and generate embeddings.

    Args:
        url_to_crawl_result: Dict mapping url -> PageCrawlResult
        batch_size: Batch size for parallel processing

    Returns:
        Dict mapping url -> EntryWithEmbedding (only includes entries where should_pursue=True)
    """
    logger.info(
        "Starting LLM processing",
        extra={
            "total_pages": len(url_to_crawl_result),
            "batch_size": batch_size,
        },
    )

    url_to_entry: dict[str, EntryWithEmbedding] = {}
    urls = list(url_to_crawl_result.keys())
    total_batches = (len(urls) + batch_size - 1) // batch_size
    batch_num = 0
    total_errors = 0

    async def process_entry(url: str) -> EntryWithEmbedding | None:
        """Parse entry and generate embedding for a single URL."""
        try:
            # Parse entry
            parsed_result = await parse_entry(
                url=url,
                html=extract_text_from_html(url_to_crawl_result[url].cleaned_html),
            )

            if not parsed_result.should_pursue:
                logger.debug(f"SKIP [{url}]: should_pursue=False")
                return None

            # Generate embedding
            title = (
                parsed_result.title.replace("\x00", " ")
                if "\x00" in parsed_result.title
                else parsed_result.title
            )
            summary = (
                parsed_result.summary.replace("\x00", " ")
                if "\x00" in parsed_result.summary
                else parsed_result.summary
            )
            text_to_embed = f"{title} {summary}"
            embedding = await generate_embedding(text_to_embed)

            # Create EntryWithEmbedding
            entry_with_embedding = EntryWithEmbedding(
                should_pursue=parsed_result.should_pursue,
                title=parsed_result.title,
                summary=parsed_result.summary,
                topics=parsed_result.topics,
                author=parsed_result.author,
                date_published=parsed_result.date_published,
                embedding=embedding,
            )

            logger.info(f'ENTRY [{url}]: "{parsed_result.title[:60]}..."')
            return entry_with_embedding

        except Exception as e:
            logger.error(f"ERROR [{url}]: {type(e).__name__}: {str(e)[:80]}")
            return None

    for i in range(0, len(urls), batch_size):
        batch_num += 1
        batch_urls = urls[i : i + batch_size]
        logger.info(
            f"LLM Batch {batch_num}/{total_batches}: Processing {len(batch_urls)} pages..."
        )

        # Process entries in parallel (parse + generate embedding)
        results = await asyncio.gather(
            *[process_entry(url) for url in batch_urls], return_exceptions=True
        )

        # Collect successful entries
        batch_entries = 0
        batch_errors = 0
        for url, result in zip(batch_urls, results):
            if isinstance(result, Exception):
                batch_errors += 1
                total_errors += 1
                logger.error(
                    f"ERROR [{url}]: {type(result).__name__}: {str(result)[:80]}"
                )
            elif result is not None and isinstance(result, EntryWithEmbedding):
                url_to_entry[url] = result
                batch_entries += 1

        logger.info(
            f"LLM Batch {batch_num} complete: {batch_entries} entries found, {batch_errors} errors"
        )

    logger.info(
        "LLM processing complete",
        extra={
            "total_entries": len(url_to_entry),
            "total_errors": total_errors,
        },
    )

    return url_to_entry


def _delete_orphaned_entries(
    url_to_entry: dict[str, EntryWithEmbedding],
    url_to_link_obj: dict[str, Link],
) -> None:
    """
    Delete entries for links that were crawled but no longer have entries (orphaned).

    Note: Links themselves are never deleted, only entries.

    Args:
        url_to_entry: Dict mapping url -> EntryWithEmbedding (only entry URLs)
        url_to_link_obj: Dict mapping url -> Link (all internal crawled URLs)
    """
    all_crawled_link_ids = {link.id for link in url_to_link_obj.values()}
    link_ids_with_entries = {url_to_link_obj[url].id for url in url_to_entry.keys()}
    link_ids_orphaned = all_crawled_link_ids - link_ids_with_entries

    if not link_ids_orphaned:
        return

    # Only delete entries for orphaned links
    stmt = select(Entry).where(Entry.link_id.in_(link_ids_orphaned))
    entries_to_delete = db.session.execute(stmt).scalars().all()

    if entries_to_delete:
        for entry in entries_to_delete:
            db.session.delete(entry)
        db.session.flush()
        logger.info(f"Deleted {len(entries_to_delete)} orphaned entries")


def _create_or_update_entries(
    url_to_entry: dict[str, EntryWithEmbedding],
    url_to_link_obj: dict[str, Link],
) -> None:
    """
    Create or update Entry objects for URLs that have entries.

    If an entry already exists for a link, it is deleted first (since link_id is unique).
    """
    if not url_to_entry:
        logger.info("No entries to create")
        return

    # Get link_ids that will have entries
    link_ids_with_entries = {
        url_to_link_obj[url].id
        for url in url_to_entry.keys()
        if url_to_link_obj[url].entry
    }

    # Delete existing entries for links that will have entries (to handle updates)
    if link_ids_with_entries:
        stmt = select(Entry).where(Entry.link_id.in_(link_ids_with_entries))
        existing_entries = db.session.execute(stmt).scalars().all()
        if existing_entries:
            for entry in existing_entries:
                db.session.delete(entry)
            db.session.flush()
            logger.info(
                f"Deleted {len(existing_entries)} existing entries to be updated"
            )

    # Create entry params with embeddings
    entry_params = []
    for url, entry in url_to_entry.items():
        # Sanitize fields
        title = (
            entry.title.replace("\x00", " ") if "\x00" in entry.title else entry.title
        )
        summary = (
            entry.summary.replace("\x00", " ")
            if "\x00" in entry.summary
            else entry.summary
        )
        author = (
            entry.author.replace("\x00", " ")
            if "\x00" in entry.author
            else entry.author
        )

        link = url_to_link_obj[url]
        params = EntryCreateParams(
            link_id=link.id,
            title=title,
            summary=summary,
            topics=entry.topics,
            author=author,
            date_published=parse_date(entry.date_published),
            embedding=entry.embedding,
        )
        entry_params.append(params)

    create_entries_batch(entry_params)
    logger.info(f"{len(entry_params)} entries created with embeddings")


def _collect_external_links(
    url_to_crawl_result: dict[str, PageCrawlResult], domain_url: str
) -> tuple[set[str], set[str], dict[str, list[str]]]:
    """Collect all external links and domains from crawl results."""
    logger.info("Processing external links...")
    external_urls_set = set()
    external_domains_set = set()
    internal_to_external_mappings: dict[
        str, list[str]
    ] = {}  # internal_url -> [external_urls]

    for source_url, crawl_result in url_to_crawl_result.items():
        external_urls = crawl_result.links.external
        if external_urls:
            external_urls_set.update(external_urls)
            internal_to_external_mappings[source_url] = external_urls
            # Extract domains from external URLs
            for ext_url in external_urls:
                ext_domain = get_domain(ext_url)
                if ext_domain != domain_url:
                    external_domains_set.add(ext_domain)

    logger.info(
        "External links processed",
        extra={
            "unique_external_urls": len(external_urls_set),
            "unique_external_domains": len(external_domains_set),
        },
    )
    return external_urls_set, external_domains_set, internal_to_external_mappings


def _create_internal_external_link_mappings(
    internal_to_external_mappings: dict[str, list[str]],
    url_to_link_obj: dict[str, Link],
    external_link_objs: dict[str, Link],
) -> None:
    """Create link mappings: internal --> external (don't care about internal ones)."""
    logger.info("Creating internal --> external link mappings...")
    # Track (source_link_id, target_link_id) pairs to prevent duplicates
    mapping_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    internal_external_mapping_params = []

    for internal_url, external_urls in internal_to_external_mappings.items():
        if internal_url not in url_to_link_obj:
            continue
        source_link = url_to_link_obj[internal_url]

        for ext_url in external_urls:
            sanitized_ext = sanitize_url(ext_url)
            if sanitized_ext not in external_link_objs:
                continue
            target_link = external_link_objs[sanitized_ext]

            # Avoid self-references
            if source_link.id == target_link.id:
                continue

            # Check for duplicates
            mapping_pair = (source_link.id, target_link.id)
            if mapping_pair in mapping_pairs:
                continue  # Skip duplicate mapping

            mapping_pairs.add(mapping_pair)
            params = LinkMappingCreateParams(
                source_link_id=source_link.id, target_link_id=target_link.id
            )
            internal_external_mapping_params.append(params)

    if internal_external_mapping_params:
        create_link_mappings_batch(internal_external_mapping_params)
        logger.info(
            f"{len(internal_external_mapping_params)} internal --> external link mappings created"
        )
    else:
        logger.debug("No internal --> external link mappings to create")


async def _validate_domain(
    http_session: aiohttp.ClientSession,
    domain: Domain,
    start_url: str,
) -> Domain:
    """
    Validate a domain by fetching HTML, classifying it, and updating the domain object.

    Args:
        http_session: HTTP session for fetching
        domain: Domain object in PENDING state
        start_url: Starting URL to fetch for classification

    Returns:
        Updated Domain object

    Raises:
        SkipCrawlingDomainException: If domain is not a blog or scraping fails
        FatalException: If validation fails critically
    """
    logger.info(f"Validating domain: {domain.domain_url}")

    try:
        # 1. Fetch HTML
        logger.info(f"Fetching HTML from {start_url}...")
        crawl_result = await crawl_url(http_session, start_url)
        html = crawl_result.cleaned_html
        logger.info("HTML fetched successfully")

        # 2. Extract text from HTML for classification (reduces token usage)
        text_content = extract_text_from_html(html)
        logger.debug(
            f"Extracted text: {len(text_content.encode('utf-8'))} bytes "
            f"(from {len(html.encode('utf-8'))} bytes HTML)"
        )

        # 3. Run classifier
        logger.info("Classifying domain...")
        classification = await classify_domain(
            url=start_url,
            html=text_content,
        )
        logger.info(
            "Classification complete",
            extra={
                "entity": classification.entity.value
                if classification.entity
                else None,
                "entity_name": classification.name,
                "blog": classification.blog,
            },
        )

        # 3. Update domain object
        domain.entity = classification.entity.value
        domain.name = classification.name

        if not classification.blog:
            domain.status = DomainStatus.NOT_A_BLOG
            db.session.flush()
            logger.warning("Domain is not a blog, marking as NOT_A_BLOG")
            raise SkipCrawlingDomainException(
                f"Domain {domain.domain_url} is not a blog"
            )

        # Domain is a blog, keep it in PENDING state for now
        db.session.flush()
        logger.info("Domain validated as blog, proceeding with scrape")

        return domain

    except SkipCrawlingDomainException:
        raise
    except FatalException as e:
        # Scraping failed - update domain status
        domain.status = DomainStatus.SCRAPING_FAILED
        domain.error_message = str(e)
        db.session.flush()
        raise SkipCrawlingDomainException(
            f"Domain {domain.domain_url} failed validation: {str(e)}"
        ) from e
    except Exception as e:
        import traceback

        traceback.print_exc()
        breakpoint()
        # Other failure
        domain.status = DomainStatus.OTHER_FAILURE
        domain.error_message = str(e)
        db.session.flush()
        raise SkipCrawlingDomainException(
            f"Domain {domain.domain_url} failed validation: {str(e)}"
        ) from e


def _create_domain_mappings(
    domain: Domain,
    external_domains_set: set[str],
    external_domain_objs: dict[str, Domain],
) -> None:
    """Create domain mappings: this domain --> other domains."""
    logger.info("Creating domain mappings...")
    domain_mapping_params = []
    for ext_domain_url in external_domains_set:
        target_domain = external_domain_objs[ext_domain_url]
        # Avoid self-references
        if domain.id == target_domain.id:
            continue

        params = DomainMappingCreateParams(
            source_domain_id=domain.id,
            target_domain_id=target_domain.id,
        )
        domain_mapping_params.append(params)

    if domain_mapping_params:
        create_domain_mappings_batch(domain_mapping_params)
        logger.info(f"{len(domain_mapping_params)} domain mappings created")
    else:
        logger.debug("No domain mappings to create")


def _index_data(
    url_to_crawl_result: dict[str, PageCrawlResult],
    url_to_entry: dict[str, EntryWithEmbedding],
    domain_url: str,
    domain: Domain,
):
    """
    Commit all data to database.

    Args:
        url_to_crawl_result: Dict mapping url -> PageCrawlResult
        url_to_entry: Dict mapping url -> EntryWithEmbedding (only entry URLs)
        domain_url: Domain URL
        domain: Domain object (already created in PENDING state)

    Returns:
        Updated Domain object
    """
    logger.info(
        "Starting database operations",
        extra={
            "domain": domain_url,
            "links_to_create": len(url_to_crawl_result),
            "entries_to_create": len(url_to_entry),
        },
    )

    # Collect external links and domains first
    (
        external_urls_set,
        external_domains_set,
        internal_to_external_mappings,
    ) = _collect_external_links(url_to_crawl_result, domain_url)

    # Get or create all external domains (internal domain already exists)
    logger.info("Getting/creating external domains...")
    all_domain_objs: dict[str, Domain] = {domain_url: domain}

    # Get existing external domains
    if external_domains_set:
        existing_domains = get_domains_by_urls(list(external_domains_set))
        all_domain_objs.update(existing_domains)

        # Create external domains that don't exist
        domain_params_to_create = []
        for ext_domain_url in external_domains_set:
            if ext_domain_url not in all_domain_objs:
                domain_params_to_create.append(
                    DomainCreateParams(
                        domain_url=ext_domain_url,
                        entity=None,
                        name=None,
                    )
                )

        if domain_params_to_create:
            created_domains = create_domains_batch(domain_params_to_create)
            for d in created_domains:
                all_domain_objs[d.domain_url] = d
            logger.info(f"Created {len(created_domains)} new external domains")

    external_domain_objs = {url: all_domain_objs[url] for url in external_domains_set}
    logger.info(f"{len(all_domain_objs)} domains ready")

    # Get or create all links (internal + external) in one batch
    logger.info("Getting/creating all links...")
    all_urls = list(url_to_crawl_result.keys()) + list(external_urls_set)
    sanitized_all_urls = [sanitize_url(url) for url in all_urls]

    # Get existing links
    existing_links = get_links_by_urls(sanitized_all_urls)
    all_link_objs: dict[str, Link] = {}
    all_link_objs.update(existing_links)

    # Create links that don't exist
    # Track sanitized URLs we're about to create to prevent duplicates
    urls_being_created: set[str] = set()
    link_params_to_create = []

    for url in url_to_crawl_result.keys():
        sanitized = sanitize_url(url)
        if sanitized not in all_link_objs and sanitized not in urls_being_created:
            link_params_to_create.append(
                LinkCreateParams(
                    url=sanitized,
                    domain_id=domain.id,
                )
            )
            urls_being_created.add(sanitized)

    for ext_url in external_urls_set:
        sanitized = sanitize_url(ext_url)
        # Skip if already exists in DB or already queued for creation
        if sanitized not in all_link_objs and sanitized not in urls_being_created:
            ext_domain = get_domain(ext_url)
            ext_domain_obj = all_domain_objs[ext_domain]
            link_params_to_create.append(
                LinkCreateParams(
                    url=sanitized,
                    domain_id=ext_domain_obj.id,
                )
            )
            urls_being_created.add(sanitized)

    if link_params_to_create:
        logger.info(f"Creating {len(link_params_to_create)} links...")
        for i, params in enumerate(link_params_to_create, 1):
            logger.debug(f"{i}. {params.url}")
        created_links = create_links_batch(link_params_to_create)
        for link in created_links:
            all_link_objs[link.url] = link
        logger.info(f"Created {len(created_links)} new links")

    # Build url_to_link_obj for internal URLs
    url_to_link_obj: dict[str, Link] = {}
    for url in url_to_crawl_result.keys():
        sanitized = sanitize_url(url)
        url_to_link_obj[url] = all_link_objs[sanitized]

    # Build external_link_objs
    external_link_objs: dict[str, Link] = {}
    for ext_url in external_urls_set:
        sanitized = sanitize_url(ext_url)
        external_link_objs[sanitized] = all_link_objs[sanitized]

    logger.info(f"{len(all_link_objs)} links ready")

    # Delete orphaned entries (links that no longer have entries)
    _delete_orphaned_entries(url_to_entry, url_to_link_obj)

    # Create or update entries for URLs that have entries
    _create_or_update_entries(url_to_entry, url_to_link_obj)

    # Create link mappings: internal --> external
    _create_internal_external_link_mappings(
        internal_to_external_mappings, url_to_link_obj, external_link_objs
    )

    # Create domain mappings: this domain --> other domains
    _create_domain_mappings(domain, external_domains_set, external_domain_objs)

    # Update domain status to SUCCESS after successful indexing
    domain.status = DomainStatus.SUCCESS
    domain.error_message = None

    logger.info("Committing transaction...")
    db.session.commit()
    logger.info("Transaction committed")

    return domain


def scrape_domain(
    url: str,
    max_depth: int = 10,
    batch_size: int = 50,
) -> None:
    """
    Main handler function that orchestrates the scraping flow.

    Args:
        url: Starting URL to scrape
        max_depth: Maximum BFS depth
        batch_size: Batch size for parallel processing

    Returns:
        Domain object

    Raises:
        SkipCrawlingDomainException: If domain already scraped
        FatalException: If scraping fails
    """
    logger.info(
        "Starting domain scrape",
        extra={
            "url": url,
            "max_depth": max_depth,
            "batch_size": batch_size,
        },
    )

    # 1. Extract domain
    url = sanitize_url(url)
    domain_url = get_domain(url)
    logger.info(f"Extracted domain: {domain_url}")

    # 2. Get or create domain (in PENDING state)
    domain = get_or_create_domain_by_url(domain_url)

    # Check if domain is already processed (not pending)
    if domain.status != DomainStatus.PENDING:
        logger.warning(
            f"Domain {domain_url} already processed (status: {domain.status.value}), skipping"
        )
        return

    logger.info("Domain is in PENDING state, proceeding with scrape...")

    # Step 0: Validate domain (fetch HTML, classify, update domain)
    logger.info("Calling _validate_domain()...")
    try:

        async def _validate():
            async with aiohttp.ClientSession() as http_session:
                await _validate_domain(
                    http_session=http_session,
                    domain=domain,
                    start_url=url,
                )

        asyncio.run(_validate())
    except SkipCrawlingDomainException as e:
        # Domain validation failed - status already updated in _validate_domain
        logger.warning(f"Domain validation failed: {str(e)}")
        db.session.commit()
        return

    # Step 1 & 2: Crawl and extract data
    try:

        async def _run_async_helpers():
            async with aiohttp.ClientSession() as http_session:
                # Step 1: BFS to collect PageCrawlResult objects
                url_to_crawl_result = await _crawl_pages(
                    http_session=http_session,
                    start_url=url,
                    domain_url=domain_url,
                    max_depth=max_depth,
                    batch_size=batch_size,
                )
                # Step 2: Process all HTML via LLM and generate embeddings
                logger.info("Calling _extract_data()...")
                url_to_entry = await _extract_data(
                    url_to_crawl_result=url_to_crawl_result, batch_size=batch_size
                )
                return url_to_crawl_result, url_to_entry

        url_to_crawl_result, url_to_entry = asyncio.run(_run_async_helpers())
    except TooManyInternalLinksException as e:
        # Too many internal links - update domain status
        domain.status = DomainStatus.OTHER_FAILURE
        domain.error_message = TOO_MANY_INTERNAL_LINKS_REASON
        db.session.commit()
        logger.warning(f"Domain {domain_url} has too many internal links: {str(e)}")
        return

    # Final summary
    logger.info(
        "FINAL SUMMARY",
        extra={
            "domain": domain_url,
            "pages_crawled": len(url_to_crawl_result),
            "entries_found": len(url_to_entry),
        },
    )

    if url_to_entry:
        logger.info("Entries found:")
        for i, (url, entry) in enumerate(url_to_entry.items(), 1):
            logger.info(
                f'{i}. "{entry.title[:60]}..."',
                extra={
                    "url": url,
                    "author": entry.author,
                    "topics": ", ".join(entry.topics[:3]),
                },
            )
    else:
        logger.info("No entries found (all pages had should_pursue=False)")

    # 5. Step 3: Commit everything to DB (sync, at the end)
    _index_data(
        url_to_crawl_result=url_to_crawl_result,
        url_to_entry=url_to_entry,
        domain_url=domain_url,
        domain=domain,
    )
