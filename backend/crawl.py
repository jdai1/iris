import asyncio
from typing import List, Tuple
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

from exc import FatalException, ScrapedRecentlyException, SkippedDomainException, TooManyTimeoutsException
from util import (
    get_date_a_week_ago,
    get_date_today,
    is_timeout_message,
    parse_date,
    print_warn,
    timing_decorator,
    print_err,
)
from url_utils import (
    add_https_if_missing,
    get_domain_and_path,
    get_domain,
    is_valid_internal_link,
    sanitize_url,
)
from agents.parse_entry import ParseEntryAgent, ParseEntryAgentOutput
from agents.classify_domain import ClassifyDomainAgent, ClassifyDomainAgentOutput
from db import (
    Entry,
    EntryDriver,
    Domain,
    SkippedDomain,
    DomainDriver,
    SkippedDomainDriver,
)

# * CONTSTANTS
PAGE_TIMEOUT_MS = 1000
BATCH_SIZE = 25

NOT_A_BLOG_OR_PERSON_REASON = "Skipped b/c website was not a blog run by an individual"
TIMEOUT_ERROR_REASON = "Skipped b/c website could not be scraped due to too many timeouts"
OTHER_ERROR_REASON = "Skipped b/c website could not be scraped due to an error"
MANUALLY_SKIPPED_REASON = "Skipped manually via the CLI"

entry_driver = EntryDriver()
domain_driver = DomainDriver()
skipped_domain_driver = SkippedDomainDriver()


""" Crawls a URL via BFS: Returns all found blog posts, external domains, and external links """


@timing_decorator
async def crawl_domain(
    url: str,
    crawler: AsyncWebCrawler,
    run_config: CrawlerRunConfig,
    batch_size: int,
) -> Tuple[List[Entry], List[str], List[str], List[str], List[str]]:
    url = sanitize_url(url)
    entries = []
    external_links: list[str] = []
    external_domains: list[str] = []

    parsed_internal_links: list[str] = []
    skipped_internal_links: list[str] = []

    internal_links_queue: list[str] = [url]
    visited: dict[str, bool] = {}

    timeout_error_links: list[str] = []
    other_error_links: list[str] = []

    # BFS through all internal (same-domain) links in batches
    while internal_links_queue:
        batch_urls = internal_links_queue[:batch_size]
        internal_links_queue = internal_links_queue[batch_size:]

        # run LLM to parse blog entry information form HTML
        tasks = [
            parse_entry(entry_url=entry_url, crawler=crawler, run_config=run_config)
            for entry_url in batch_urls
        ]

        # run tasks async
        results = await asyncio.gather(*tasks, return_exceptions=True)
        new_internal_links_batch = []
        new_external_links_batch = []
        new_external_domains_batch = []
        new_entry_urls = []
        new_skipped_urls = []
        
        for current_url, res in zip(batch_urls, results):
            if isinstance(res, BaseException):
                if is_timeout_message(res.args[0]):
                    timeout_error_links.append(current_url)
                    print_err(f"A timeout exception occurred: {res}")
                else:
                    other_error_links.append(current_url)
                    print_err(f"Some error occurred: {res}")
                continue
            is_blog, entry, new_internal_links, new_external_links = res

            if is_blog:
                entries.append(entry)
                new_entry_urls.append(entry.entry_url)
            else:
                new_skipped_urls.append(entry.entry_url)

            assert current_url == sanitize_url(current_url)
            assert current_url not in visited

            # add current url to visited
            visited[current_url] = True

            # NOTE: links are sanitized in parse_entry(...)
            new_external_domains_batch += [
                get_domain(link) for link in new_external_links
            ]
            new_external_links_batch += [link for link in new_external_links]
            new_internal_links_batch += [link for link in new_internal_links]

        new_internal_links_batch = [
            l for l in new_internal_links_batch if l not in visited
        ]
        internal_links_queue = list(
            set(new_internal_links_batch + internal_links_queue)
        )
        parsed_internal_links = list(set(new_entry_urls + parsed_internal_links))
        skipped_internal_links = list(set(new_skipped_urls + skipped_internal_links))
        external_links = list(set(new_external_links_batch + external_links))
        external_domains = list(set(new_external_domains_batch + external_domains))

        print(f"added {len(new_entry_urls)} blog posts: {new_entry_urls}")
        print(f"skipped {len(new_skipped_urls)} blog posts: {new_skipped_urls}")
        print("# internal links", len(internal_links_queue))
        print("# external domains", len(external_domains))
        print("# visited", len(visited))

        # * If more than 20% of all crawls are timing out, then throw an error.
        if len(timeout_error_links) / len(visited) > 0.2:
            raise TooManyTimeoutsException(f"len(timeout_error_links) / len(visited) = {len(timeout_error_links) / len(visited)} > 0.2")

    return (
        entries,
        external_domains,
        external_links,
        parsed_internal_links,
        skipped_internal_links
    )


async def parse_entry(
    entry_url: str, crawler: AsyncWebCrawler, run_config: CrawlerRunConfig
):
    # crawl
    print(add_https_if_missing(entry_url))
    result = await crawler.arun(
        url=add_https_if_missing(entry_url), config=run_config, verbose=False
    )
    if not result.success:
        raise Exception(f"Something went wrpong when scraping this URL: {entry_url}. Error message: {result.error_message}")

    # grab internal / external links
    internal_links = [
        sanitize_url(link["href"])
        for link in result.links.get("internal", [])
        if is_valid_internal_link(entry_url=entry_url, href=link["href"])
    ]
    external_links = [
        sanitize_url(link["href"]) for link in result.links.get("external", [])
    ]

    # parse entry
    entry_parser = ParseEntryAgent()
    entry_parser_res = await entry_parser.async_call(
        url=entry_url, html=result.cleaned_html
    )
    assert isinstance(entry_parser_res.structured_output, ParseEntryAgentOutput)
    parsed_entry = entry_parser_res.structured_output  # type: ignore

    # NOTE: For some reason, sometimes, the fields will contain null bytes in them...
    if "\x00" in parsed_entry.title:
        parsed_entry.title = parsed_entry.title.replace("\x00", " ")
    if "\x00" in parsed_entry.summary:
        parsed_entry.summary = parsed_entry.summary.replace("\x00", " ")
    if "\x00" in parsed_entry.author:
        parsed_entry.author = parsed_entry.author.replace("\x00", " ")
    entry = Entry(
        title=parsed_entry.title,
        summary=parsed_entry.summary,
        topics=parsed_entry.topics,
        author=parsed_entry.author,
        date_published=parse_date(parsed_entry.date_published),
        links=set(internal_links + external_links),
        entry_url=get_domain_and_path(entry_url),
        domain_url=get_domain(entry_url),
    )

    return parsed_entry.is_blog, entry, internal_links, external_links


async def classify_domain(
    url: str, crawler: AsyncWebCrawler, run_config: CrawlerRunConfig
) -> ClassifyDomainAgentOutput:
    url = add_https_if_missing(url)
    crawler_res = await crawler.arun(url=url, config=run_config, verbose=False)

    if not crawler_res.success:
        raise Exception("Something went wrong when scraping this URL:", url)

    domain_classifier_agent = ClassifyDomainAgent()
    domain_classifier_res = await domain_classifier_agent.async_call(
        url=url, html=crawler_res.cleaned_html
    )

    assert isinstance(
        domain_classifier_res.structured_output, ClassifyDomainAgentOutput
    )
    return domain_classifier_res.structured_output


async def ingest(url: str):
    # init crawler
    crawler = AsyncWebCrawler(config=BrowserConfig())
    run_config = CrawlerRunConfig(page_timeout=PAGE_TIMEOUT_MS, verbose=False)
    await crawler.start()

    # pre-process url
    url = sanitize_url(url)
    domain_url = get_domain(url)

    if skipped_domain_driver.contains_skipped_domain(domain_url):
        # NOTE: implicit assumption that skipped domains will not become domains of interest in the future
        raise SkippedDomainException(f"Skipping {domain_url} b/c it is already present in the SkippedDomain table")

    if domain_driver.contains_domain(domain_url):
        domain = domain_driver.get_domain(domain_url)
        if (
            domain.date_last_scraped is not None
            and domain.date_last_scraped > get_date_a_week_ago()
        ):
            raise ScrapedRecentlyException(f"Skipping {domain_url} b/c it was scraped less than a week ago")
    else:
        try:
            domain_classifier_res = await classify_domain(
                url=url, crawler=crawler, run_config=run_config
            )
        except BaseException as e:
            raise FatalException(f"Skipping {domain_url} b/c scraping failed with error: {e}")

        if not domain_classifier_res.blog or domain_classifier_res.entity != "person":
            # if the url isn't a blog run by a person, add to skipped domains
            skipped_domain_driver.add_skipped_domain(
                domain=SkippedDomain(domain_url=get_domain(url), entity=domain_classifier_res.entity, reason=NOT_A_BLOG_OR_PERSON_REASON)
            )
            raise SkippedDomainException(f"Skipping {domain_url} b/c this domain wasn't a blog run by an individual")

        # add domain to db
        domain_driver.add_domain(
            Domain(
                domain_url=domain_url,
                entity=domain_classifier_res.entity,
                name=domain_classifier_res.name,
                external_domains=[],  # init to empty
                external_links=[],  # init to empty
                parsed_internal_links=[],  # init to empty
                skipped_internal_links=[],  # init to empty
                date_last_scraped=None,  # init to None
            )
        )

    response = input(f"\033[1;32mScraping: {domain_url} — Press Y to scrape and anything else to skip:\033[0m ").strip().upper()
    if response != "Y":
        skipped_domain_driver.add_skipped_domain(
                domain=SkippedDomain(domain_url=get_domain(url), entity=domain_classifier_res.entity, reason=NOT_A_BLOG_OR_PERSON_REASON)
            )
        return

    batch_size = BATCH_SIZE
    for i in range(3):
        try:
            # crawl
            (
                entries,
                external_domains,
                external_links,
                parsed_internal_links,
                skipped_internal_links
            ) = await crawl_domain(
                url=url, crawler=crawler, run_config=run_config, batch_size=BATCH_SIZE
            )

            # add entries, external domains, & external links to db
            print(f"Adding {len(entries)} entries")
            entry_driver.add_entries(entries=entries)
            domain_driver.update_external_links_and_domains(
                domain_url=get_domain(url),
                external_domains=external_domains,
                external_links=external_links,
                parsed_internal_links=parsed_internal_links,
                skipped_internal_links=skipped_internal_links,
                date_last_scraped=get_date_today(),
            )
            await crawler.close()
            return
        except TooManyTimeoutsException as e:
            batch_size = batch_size // 2
            print_warn(f"{str(e)}. Trying again with batch_size: {batch_size}.")
        except Exception as e:
            # TODO: add to skipped domians w/ reason: "other error"
            raise FatalException(f"Could not scrape domain: {domain_url} due to error: {e}")
        
        
    await crawler.close()
    # TODO: add to skipped domians w/ reason: "timeouts error"
    raise FatalException(f"Could not scrape domain: {domain_url} due to timeout issues")


async def spider(url: str):
    domain_url = get_domain(url)
    print(f"Domain '{domain_url}' has not been processed yet -- Scraping now")
    try:
        await ingest(domain_url)
    except FatalException as e:
        print(
            f"TERMINATING; Failed to scrape starting node ({domain_url}) b/c of error: {e}"
        )
        return
    else:
        print(f"CONTINUING: {e}")

    domain = domain_driver.get_domain(domain_url)
    for one_hop_domain_url in domain.external_domains:
        try:
            await ingest(url=one_hop_domain_url)
        except Exception as e:
            print(
                f"CONTINUING TO NEXT NODE; Failed to scrape a one-hop domain ({one_hop_domain_url}) b/c of error: {e}"
            )


if __name__ == "__main__":
    # asyncio.run(spider("https://thume.ca/"))
    # asyncio.run(spider("https://bigdanzblog.wordpress.com/"))
    asyncio.run(spider("projects.drogon.net"))
