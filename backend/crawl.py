import asyncio
import traceback
from typing import List, Tuple
from crawl4ai import AsyncWebCrawler
from crawl4ai.models import CrawlResult
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

from exc import FatalException, SkipCrawlingDomainException, TooManyCrawlingTimeoutsException, TooManyInternalLinks
from util import (
    assert_and_get_single_crawl_result,
    get_date_a_month_ago,
    get_date_today,
    is_timeout_message,
    parse_date,
    print_ok,
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
    ExcludedDomain,
    DomainDriver,
    ExcludedDomainDriver,
)

# * CONTSTANTS
PAGE_TIMEOUT_MS = 5000
BATCH_SIZE = 25
MAX_INTERNAL_LINKS_Q_SIZE = 1000

NOT_A_BLOG_OR_PERSON_REASON = "Excluded b/c website was not a blog run by an individual"
TIMEOUT_ERROR_REASON = "Excluded b/c website could not be scraped due to too many timeouts"
OTHER_ERROR_REASON = "Excluded b/c website could not be scraped due to an error"
MANUALLY_EXCLUDED_REASON = "Excluded manually via the CLI"
TOO_MANY_INTERNAL_LINKS_REASON = "Excluded b/c too many internal links to process."

entry_driver = EntryDriver()
domain_driver = DomainDriver()
excluded_domain_driver = ExcludedDomainDriver()

""" Crawls a URL via BFS: Returns all found blog posts, external domains, and external links """

@timing_decorator
async def crawl_domain(
    url: str,
    domain_url: str,
    crawler: AsyncWebCrawler,
    run_config: CrawlerRunConfig,
    batch_size: int,
) -> Tuple[List[Entry], List[str], List[str], List[str], List[str]]:
    url = sanitize_url(url)
    entries = []
    external_links: list[str] = []
    external_domains: list[str] = []

    target_internal_links: list[str] = []
    nontarget_internal_links: list[str] = []

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
            parse_entry(entry_url=entry_url, domain_url=domain_url, crawler=crawler, run_config=run_config)
            for entry_url in batch_urls
        ]

        # run tasks async
        results = await asyncio.gather(*tasks, return_exceptions=True)
        new_internal_links_batch = []
        new_external_links_batch = []
        new_external_domains_batch = []
        new_target_links = []
        new_nontarget_links = []
        
        for current_url, res in zip(batch_urls, results):
            if isinstance(res, BaseException):
                if len(res.args) >= 1 and is_timeout_message(res.args[0]):
                    timeout_error_links.append(current_url)
                    print_err(f"A timeout exception occurred: {res}")
                else:
                    other_error_links.append(current_url)
                    print_err(f"Some error occurred: {res}")
                continue
            is_blog, entry, new_internal_links, new_external_links = res

            if is_blog:
                entries.append(entry)
                new_target_links.append(entry.entry_url)
            else:
                new_nontarget_links.append(entry.entry_url)

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
        target_internal_links = list(set(new_target_links + target_internal_links))
        nontarget_internal_links = list(set(new_nontarget_links + nontarget_internal_links))
        external_links = list(set(new_external_links_batch + external_links))
        external_domains = list(set(new_external_domains_batch + external_domains))

        print(f"added {len(new_target_links)} blog posts: {new_target_links}")
        print(f"skipped {len(new_nontarget_links)} blog posts: {new_nontarget_links}")
        print("# internal links", len(internal_links_queue))
        print("# external domains", len(external_domains))
        print("# visited", len(visited))

        # * If more than 20% of all crawls are timing out, then throw an error.
        if len(timeout_error_links) / len(visited) > 0.2:
            raise TooManyCrawlingTimeoutsException(f"len(timeout_error_links) / len(visited) = {len(timeout_error_links) / len(visited)} > 0.2")

        if len(internal_links_queue) > MAX_INTERNAL_LINKS_Q_SIZE:
            raise TooManyInternalLinks(f"{len(internal_links_queue)} links —— too many!")

    return (
        entries,
        external_domains,
        external_links,
        target_internal_links,
        nontarget_internal_links
    )


async def parse_entry(
    entry_url: str, domain_url: str, crawler: AsyncWebCrawler, run_config: CrawlerRunConfig
):
    # crawl
    print(add_https_if_missing(entry_url))
    
    crawler_res = assert_and_get_single_crawl_result(await crawler.arun(
        url=add_https_if_missing(entry_url), config=run_config
    ))
    assert crawler_res.redirected_url is not None
    assert crawler_res.cleaned_html is not None
    
    entry_url = sanitize_url(crawler_res.redirected_url)

    if not is_valid_internal_link(domain_url=domain_url, href=entry_url):
        raise Exception(f"Link {domain_url} redirected to something that wasn't in the same domain as the entry_url ({entry_url})")
    if not crawler_res.success:
        raise Exception(f"Something went wrong when scraping this URL: {entry_url}. Error message: {crawler_res.error_message}")

    # grab internal / external links
    internal_links = [
        sanitize_url(link["href"])
        for link in crawler_res.links.get("internal", [])
        if is_valid_internal_link(domain_url=domain_url, href=link["href"])
    ]
    external_links = [
        sanitize_url(link["href"]) for link in crawler_res.links.get("external", [])
    ]

    # parse entry
    entry_parser = ParseEntryAgent()
    entry_parser_res = await entry_parser.async_call(
        url=entry_url, html=crawler_res.cleaned_html
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
        domain_url=domain_url,
    )

    return parsed_entry.should_pursue, entry, internal_links, external_links


async def classify_domain(
    url: str, cleaned_html: str
) -> ClassifyDomainAgentOutput:
    domain_classifier_agent = ClassifyDomainAgent()
    domain_classifier_res = await domain_classifier_agent.async_call(url=url, html=cleaned_html)
    assert isinstance(domain_classifier_res.structured_output, ClassifyDomainAgentOutput)
    return domain_classifier_res.structured_output


def is_valid_individual_blog(domain_classifier_res: ClassifyDomainAgentOutput) -> bool:
    return not domain_classifier_res.blog or domain_classifier_res.entity != "person"


async def get_domain_url_and_html_after_redirects(url: str, crawler: AsyncWebCrawler, run_config: CrawlerRunConfig) -> Tuple[str, str]:
    # initial crawl
    try:
        crawler_res = assert_and_get_single_crawl_result(await crawler.arun(url=url, config=run_config))

        assert crawler_res.success
        assert crawler_res.redirected_url is not None
        assert crawler_res.cleaned_html is not None

        # return the redirected URL, which might be different than the input URL
        return get_domain(crawler_res.redirected_url), crawler_res.cleaned_html
    except Exception as e:
        raise FatalException(f"Crawling {url} failed with error: {str(e)}")

def raise_exception_if_domain_already_exists_in_any_table(domain_url: str):
    # raise exception if the Domains table already contains a row corresponding to domain_url
    if domain_driver.contains_domain(domain_url):
        raise SkipCrawlingDomainException(f"Skipping {domain_url} b/c it has already been scraped (it is present in the Domains table)")

    # raise exception if the ExcludedDomains table already contains a row corresponding to domain_url
    if excluded_domain_driver.contains_excluded_domain(domain_url):
        raise SkipCrawlingDomainException(f"Skipping {domain_url} b/c it is already present in the ExcludedDomains table")


async def ingest(url: str):
    # sanitize URL, get domain_url pre-redirects
    url = sanitize_url(url)
    domain_url = get_domain(url)
    raise_exception_if_domain_already_exists_in_any_table(domain_url)

    # init crawler
    crawler = AsyncWebCrawler(config=BrowserConfig())
    run_config = CrawlerRunConfig(page_timeout=PAGE_TIMEOUT_MS, verbose=False)
    await crawler.start()

    # crawl url, get domain_url post-redirects & html
    domain_url, cleaned_html = await get_domain_url_and_html_after_redirects(url=url, crawler=crawler, run_config=run_config)
    raise_exception_if_domain_already_exists_in_any_table(domain_url)

    # clasify domain to determine if we should pursue it
    domain_classifier_res = await classify_domain(url=url, cleaned_html=cleaned_html)
    
    # if the url isn't a blog run by a person, add to ExcludedDomains table
    if is_valid_individual_blog(domain_classifier_res):    
        excluded_domain_driver.add_excluded_domain(
            domain=ExcludedDomain(domain_url=domain_url, entity=domain_classifier_res.entity, reason=NOT_A_BLOG_OR_PERSON_REASON)
        )
        raise SkipCrawlingDomainException("This domain isn't a blog run by an individual. Adding to ExcludedDomains table...")

    # get user confirmation
    response = input(f"\033[1;32mScraping: {domain_url} — Press Y to scrape and anything else to skip & add to ExcludedDomains table (e.g. blacklist):\033[0m ").strip().upper()
    if response != "Y":
        excluded_domain_driver.add_excluded_domain(
            domain=ExcludedDomain(domain_url=domain_url, entity=domain_classifier_res.entity, reason=NOT_A_BLOG_OR_PERSON_REASON)
        )
        raise SkipCrawlingDomainException("User Input from CLI; Adding to ExcludedDomains table...")

    # perform full crawl with retry logic
    batch_size = BATCH_SIZE
    for i in range(3):
        try:
            # crawl
            (
                entries,
                external_domains,
                external_links,
                target_internal_links,
                nontarget_internal_links
            ) = await crawl_domain(
                url=url, domain_url=domain_url, crawler=crawler, run_config=run_config, batch_size=BATCH_SIZE
            )

            # add domain to db
            print_ok(f"Adding domain ({domain_url}) to DB")
            domain_driver.add_domain(
                Domain(
                    domain_url=domain_url,
                    entity=domain_classifier_res.entity,
                    name=domain_classifier_res.name,
                    external_domains=external_domains,
                    external_links=external_links,
                    target_internal_links=target_internal_links,
                    nontarget_internal_links=nontarget_internal_links,
                    date_last_scraped=get_date_today(),
                )
            )
            # add entries
            print_ok(f"Adding {len(entries)} entries to DB")
            entry_driver.add_entries(entries=entries)
            
            await crawler.close()
            return
        except TooManyCrawlingTimeoutsException as e:
            batch_size = batch_size // 2
            print_warn(f"{str(e)}. Trying again with batch_size: {batch_size}.")
        except TooManyInternalLinks as e:
            excluded_domain_driver.add_excluded_domain(
                domain=ExcludedDomain(domain_url=domain_url, entity=domain_classifier_res.entity, reason=TOO_MANY_INTERNAL_LINKS_REASON)
            )
            raise FatalException(f"Could not scrape domain: {domain_url} due to error: {e}; Adding to ExcludedDomains table...")
        except Exception as e:
            excluded_domain_driver.add_excluded_domain(
                domain=ExcludedDomain(domain_url=domain_url, entity=domain_classifier_res.entity, reason=OTHER_ERROR_REASON)
            )
            tb_str = traceback.format_exc()
            print_err(tb_str)
            raise FatalException(f"Could not scrape domain: {domain_url} due to error: {e}; Adding to ExcludedDomains table...")
        
    await crawler.close()
    excluded_domain_driver.add_excluded_domain(
        domain=ExcludedDomain(domain_url=domain_url, entity=domain_classifier_res.entity, reason=TIMEOUT_ERROR_REASON)
    )
    raise FatalException(f"Could not scrape domain: {domain_url} due to timeout issues")


async def spider(url: str):
    domain_url = get_domain(url)
    
    # TODO: Add expiration date —— if the domain hasn't been scraped in a month, re-scrape
    # Things to think about: what things do we keep from before and what things do we want to overwrite?
    # Do we want to just delete all rows in the DB associated with this domain and re-ingest it completely?
    
    try:
        await ingest(domain_url)
    except SkipCrawlingDomainException as e:
        print_warn(
            f"SKIPPING {domain_url}: {e}"
        )
    except FatalException as e:
        print(
            f"TERMINATING; Failed to scrape starting node ({domain_url}) b/c of error: {e}"
        )
        return

    domain = domain_driver.get_domain(domain_url)
    for one_hop_domain_url in domain.external_domains:
        if domain_driver.contains_domain(one_hop_domain_url):
            print_warn(f"SKIPPING {one_hop_domain_url} b/c already scraped")
            continue
        
        try:
            await ingest(url=one_hop_domain_url)
        except SkipCrawlingDomainException as e:
            print_warn(
                f"SKIPPING {one_hop_domain_url}: {e}"
            )
        except FatalException as e:
            print_err(
                f"FATAL EXCEPTION; Failed to scrape a one-hop domain ({one_hop_domain_url}) b/c of error: {e}"
            )


# async def test(url: str):
#     crawler = AsyncWebCrawler(config=BrowserConfig())
#     run_config = CrawlerRunConfig(page_timeout=PAGE_TIMEOUT_MS, verbose=False)
#     await crawler.start()

#     result = await crawler.arun(
#         url=add_https_if_missing(url), config=run_config
#     )
#     print(result)

#     await crawler.close()

if __name__ == "__main__":
    asyncio.run(spider("https://thume.ca/"))
    # asyncio.run(spider("https://bigdanzblog.wordpress.com/"))
    # asyncio.run(spider("projects.drogon.net"))
    # asyncio.run(spider("filippo.io"))