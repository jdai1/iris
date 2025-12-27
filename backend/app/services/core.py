import asyncio

import aiohttp

from constants import URL_DEPTH_TOLERANCE, URL_REPETITION_TOLERANCE
from schemas.llm import EntryParseResult
from services.llm_services import parse_entry
from schemas.crawl import PageCrawlResult
from utils.scrape_utils import crawl_url
from utils.url_utils import (
    get_domain,
    get_url_depth,
    get_url_path_count,
    is_from_same_domain_or_subdomain,
    is_id_or_static_resource,
    sanitize_url,
)


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
    print(f"\n{'=' * 70}")
    print(f"[_crawl_pages] Starting BFS crawl")
    print(f"  Start URL: {start_url}")
    print(f"  Domain: {domain_url}")
    print(f"  Max depth: {max_depth}, Batch size: {batch_size}")
    print(f"{'=' * 70}")

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
                    print(f"    ⊘ SKIP (already visited): {url}")
                elif depth >= max_depth:
                    print(f"    ⊘ SKIP (max depth reached): {url} (depth={depth})")
                continue
            visited.add(url)
            batch.append((url, depth))

        if not batch:
            break

        batch_num += 1
        print(
            f"\n[Batch {batch_num}] Fetching {len(batch)} URLs (queue: {len(queue)}, crawled: {len(url_to_crawl_result)})"
        )
        for url, depth in batch:
            print(f"  [depth={depth}] {url}")

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
                print(f"  ✗ ERROR [{url}]: {type(result).__name__}: {str(result)[:80]}")
                continue

            crawl_result = result
            final_url = crawl_result.redirected_url

            # Handle redirects
            if final_url != url:
                final_url = sanitize_url(final_url)
                print(f"  → REDIRECT [{url}] → [{final_url}]")
                if not _is_valid_internal_link(domain_url, final_url):
                    print(f"    ✗ SKIP: Redirect target not valid internal link")
                    continue
                if final_url in visited:
                    print(f"    ✗ SKIP: Redirect target already visited")
                    continue

            # Store crawl result
            url_to_crawl_result[final_url] = crawl_result
            batch_success += 1

            # Extract internal links for queue
            internal_links = crawl_result.links.internal
            external_links = crawl_result.links.external
            print(
                f"    Processing {len(internal_links)} internal links from {final_url}..."
            )
            for link in internal_links:
                link = sanitize_url(link)
                if link in visited:
                    print(f"      ⊘ SKIP (visited): {link}")
                    continue
                if not _is_valid_internal_link(domain_url, link):
                    print(f"      ⊘ SKIP (invalid): {link}")
                    continue
                queue.append((link, depth + 1))
                new_links_added += 1
                print(f"      ✓ QUEUED (depth={depth + 1}): {link}")

            print(
                f"  ✓ [{final_url}] - {len(internal_links)} internal, {len(external_links)} external links"
            )

        print(
            f"[Batch {batch_num} complete] ✓ {batch_success} OK, ✗ {batch_errors} errors, +{new_links_added} new links queued"
        )

    print(f"\n{'=' * 70}")
    print(f"[_crawl_pages] COMPLETE")
    print(f"  Total pages crawled: {len(url_to_crawl_result)}")
    print(f"  Total errors: {total_errors}")
    print(f"  Total batches: {batch_num}")
    print(f"{'=' * 70}\n")

    return url_to_crawl_result


async def _extract_data(
    url_to_crawl_result: dict[str, PageCrawlResult], batch_size: int = 10
) -> dict[str, EntryParseResult]:
    """
    Process all HTML via LLM to extract entries.

    Args:
        url_to_crawl_result: Dict mapping url -> PageCrawlResult
        batch_size: Batch size for parallel processing

    Returns:
        Dict mapping url -> EntryParseResult (only includes entries where should_pursue=True)
    """
    print(f"\n{'=' * 70}")
    print(f"[_extract_data] Starting LLM processing")
    print(f"  Total pages to process: {len(url_to_crawl_result)}")
    print(f"  Batch size: {batch_size}")
    print(f"{'=' * 70}")

    url_to_entry: dict[str, EntryParseResult] = {}
    urls = list(url_to_crawl_result.keys())
    total_batches = (len(urls) + batch_size - 1) // batch_size
    batch_num = 0
    total_errors = 0

    for i in range(0, len(urls), batch_size):
        batch_num += 1
        batch_urls = urls[i : i + batch_size]
        print(
            f"\n[LLM Batch {batch_num}/{total_batches}] Processing {len(batch_urls)} pages..."
        )
        for url in batch_urls:
            print(f"  → {url}")

        # Process HTML in parallel
        parse_tasks = [
            parse_entry(url=url, html=url_to_crawl_result[url].cleaned_html)
            for url in batch_urls
        ]
        parsed_results = await asyncio.gather(*parse_tasks, return_exceptions=True)

        # Filter successful results where should_pursue=True
        batch_entries = 0
        batch_errors = 0
        for url, parsed_result in zip(batch_urls, parsed_results):
            if isinstance(parsed_result, Exception):
                batch_errors += 1
                total_errors += 1
                print(
                    f"  ✗ ERROR [{url}]: {type(parsed_result).__name__}: {str(parsed_result)[:80]}"
                )
                continue

            if parsed_result.should_pursue:
                url_to_entry[url] = parsed_result
                batch_entries += 1
                print(f'  ✓ ENTRY [{url}]: "{parsed_result.title[:60]}..."')
            else:
                print(f"  ⊘ SKIP [{url}]: should_pursue=False")

        print(
            f"[LLM Batch {batch_num} complete] ✓ {batch_entries} entries found, ✗ {batch_errors} errors"
        )

    print(f"\n{'=' * 70}")
    print(f"[_extract_data] COMPLETE")
    print(f"  Total entries extracted: {len(url_to_entry)}")
    print(f"  Total errors: {total_errors}")
    print(f"{'=' * 70}\n")

    return url_to_entry


def _save_data_to_db(
    url_to_crawl_result: dict[str, PageCrawlResult],
    url_to_entry: dict[str, EntryParseResult],
    domain_url: str,
):
    """
    Commit all data to database.

    Args:
        url_to_crawl_result: Dict mapping url -> PageCrawlResult
        url_to_entry: Dict mapping url -> EntryParseResult (only entry URLs)
        domain_url: Domain URL

    Returns:
        Created Domain object
    """
    print(f"\n{'=' * 70}")
    print(f"[_save_data_to_db] Starting database operations")
    print(f"  Domain: {domain_url}")
    print(f"  Links to create: {len(url_to_crawl_result)}")
    print(f"  Entries to create: {len(url_to_entry)}")
    print(f"{'=' * 70}")

    # Lazy imports to avoid DB dependency when just testing scraper
    import db
    from dao.domain import create_domain
    from dao.entry import create_entries_batch
    from dao.link import create_links_batch
    from dao.mappings import create_link_mappings_batch
    from models.models import Domain, Entry, Link
    from schemas.crawl import LinkMappingCreateParams
    from utils.date_utils import parse_date

    # Create Domain
    print(f"[_save_data_to_db] Creating domain...")
    domain = Domain(
        domain_url=domain_url,
        entity="person",  # Would come from classification in real implementation
        name="Unknown",  # Would come from classification in real implementation
        excluded=False,
        reason=None,
    )
    create_domain(domain)
    print(f"  ✓ Domain created: {domain.id}")

    # Create Links for all URLs
    print(f"[_save_data_to_db] Creating {len(url_to_crawl_result)} links...")
    links = []
    url_to_link_obj: dict[str, Link] = {}
    for url in url_to_crawl_result.keys():
        link = Link(url=sanitize_url(url), domain_id=domain.id)
        links.append(link)
        url_to_link_obj[url] = link

    create_links_batch(links)
    print(f"  ✓ {len(links)} links created")

    # Create Entries for URLs that have entries
    entries = []
    for url, parsed_entry in url_to_entry.items():
        # Sanitize fields
        title = (
            parsed_entry.title.replace("\x00", " ")
            if "\x00" in parsed_entry.title
            else parsed_entry.title
        )
        summary = (
            parsed_entry.summary.replace("\x00", " ")
            if "\x00" in parsed_entry.summary
            else parsed_entry.summary
        )
        author = (
            parsed_entry.author.replace("\x00", " ")
            if "\x00" in parsed_entry.author
            else parsed_entry.author
        )

        link = url_to_link_obj[url]
        entry = Entry(
            link_id=link.id,
            title=title,
            summary=summary,
            topics=parsed_entry.topics,
            author=author,
            date_published=parse_date(parsed_entry.date_published),
        )
        entries.append(entry)

    create_entries_batch(entries)
    print(f"  ✓ {len(entries)} entries created")

    # Create LinkMappings: for each entry URL, map to all links found on that page
    print(f"[_save_data_to_db] Creating link mappings...")
    link_mapping_params = []
    for source_url in url_to_entry.keys():
        if source_url not in url_to_link_obj:
            continue
        source_link = url_to_link_obj[source_url]

        # Get all links (internal + external) from the crawl result
        crawl_result = url_to_crawl_result[source_url]
        for target_url in crawl_result.links.internal + crawl_result.links.external:
            if target_url not in url_to_link_obj:
                continue
            target_link = url_to_link_obj[target_url]

            # Avoid self-references
            if source_link.id == target_link.id:
                continue

            params = LinkMappingCreateParams(
                source_link_id=source_link.id, target_link_id=target_link.id
            )
            link_mapping_params.append(params)

    if link_mapping_params:
        create_link_mappings_batch(link_mapping_params)
        print(f"  ✓ {len(link_mapping_params)} link mappings created")
    else:
        print(f"  ⊘ No link mappings to create")

    print(f"[_save_data_to_db] Committing transaction...")
    db.session.commit()
    print(f"  ✓ Transaction committed")
    print(f"{'=' * 70}\n")

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
    print(f"\n{'#' * 70}")
    print(f"# [scrape_domain] Starting domain scrape")
    print(f"#   URL: {url}")
    print(f"#   Max depth: {max_depth}, Batch size: {batch_size}")
    print(f"{'#' * 70}")

    # 1. Extract domain
    url = sanitize_url(url)
    domain_url = get_domain(url)
    print(f"[scrape_domain] Extracted domain: {domain_url}")

    # 2. Validate (check if already scraped) - SKIPPED for testing
    # if get_domain_by_url(domain_url):
    #     raise SkipCrawlingDomainException(
    #         f"Domain {domain_url} has already been scraped"
    #     )

    # 3. Step 1 & 2: Run async helpers (BFS and LLM processing)
    print(f"[scrape_domain] Calling _crawl_pages()...")

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
            # Step 2: Process all HTML via LLM
            print(f"[scrape_domain] Calling _extract_data()...")
            url_to_entry = await _extract_data(
                url_to_crawl_result=url_to_crawl_result, batch_size=batch_size
            )
            return url_to_crawl_result, url_to_entry

    url_to_crawl_result, url_to_entry = asyncio.run(_run_async_helpers())

    # Final summary
    print(f"\n{'#' * 70}")
    print(f"# [scrape_domain] FINAL SUMMARY")
    print(f"#   Domain: {domain_url}")
    print(f"#   Pages crawled: {len(url_to_crawl_result)}")
    print(f"#   Entries found: {len(url_to_entry)}")
    print(f"{'#' * 70}")

    if url_to_entry:
        print(f"\nEntries found:")
        for i, (url, entry) in enumerate(url_to_entry.items(), 1):
            print(f'  {i}. "{entry.title[:60]}..."')
            print(f"     URL: {url}")
            print(f"     Author: {entry.author}, Topics: {', '.join(entry.topics[:3])}")
    else:
        print(f"\nNo entries found (all pages had should_pursue=False)")

    print(f"\n{'#' * 70}\n")

    # # 5. Step 3: Commit everything to DB (sync, at the end)
    # domain = _save_data_to_db(
    #     url_to_crawl_result=url_to_crawl_result,
    #     url_to_entry=url_to_entry,
    #     domain_url=domain_url,
    # )

    # return domain
