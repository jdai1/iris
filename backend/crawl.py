import asyncio
from dataclasses import dataclass
import traceback
from typing import Dict, List, Optional, Tuple, cast
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig
from crawl4ai.models import CrawlResultContainer

from exc import (
    FatalException,
    SkipCrawlingDomainException,
    TooManyCrawlingTimeoutsException,
    TooManyInternalLinks,
)
from util import (
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
    get_domain,
    is_id_or_static_resource,
    is_from_same_domain_or_subdomain,
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
TIMEOUT_ERROR_REASON = (
    "Excluded b/c website could not be scraped due to too many timeouts"
)
OTHER_ERROR_REASON = "Excluded b/c website could not be scraped due to an error"
MANUALLY_EXCLUDED_REASON = "Excluded manually via the CLI"
TOO_MANY_INTERNAL_LINKS_REASON = "Excluded b/c too many internal links to process."


@dataclass
class MyCrawlResult:
    url: str
    success: bool
    redirected_url: str
    cleaned_html: str
    links: Dict[str, List[Dict]]
    


""" Crawls a URL via BFS: Returns all found blog posts, external domains, and external links """


class Crawler:
    def __init__(self) -> None:
        self.crawler = AsyncWebCrawler(config=BrowserConfig())
        self.run_config = CrawlerRunConfig(page_timeout=PAGE_TIMEOUT_MS, verbose=False)

        self.entry_driver = EntryDriver()
        self.domain_driver = DomainDriver()
        self.excluded_domain_driver = ExcludedDomainDriver()

    async def spider(self, url: str):
        # TODO: Add expiration date —— if the domain hasn't been scraped in a month, re-scrape
        # Things to think about: what things do we keep from before and what things do we want to overwrite?
        # Do we want to just delete all rows in the DB associated with this domain and re-ingest it completely?

        await self.crawler.start()
        domain = None
        try:
            domain = await self.ingest(url)
        except SkipCrawlingDomainException as e:
            print_warn(f"SKIPPING {url}: {e}")
        except FatalException as e:
            print(
                f"TERMINATING; Failed to scrape starting node ({url}) b/c of error: {e}"
            )
            await self.crawler.close()
            return

        if domain is None:
            domain = await self._get_domain(url)
        assert domain is not None
        
        for one_hop_domain_url in domain.external_domains:
            if self.domain_driver.contains_domain(one_hop_domain_url):
                print_warn(f"SKIPPING {one_hop_domain_url} b/c already scraped")
            else:
                try:
                    await self.ingest(url=one_hop_domain_url)
                except SkipCrawlingDomainException as e:
                    print_warn(f"SKIPPING {one_hop_domain_url}: {e}")
                except FatalException as e:
                    print_err(
                        f"FATAL EXCEPTION; Failed to scrape a one-hop domain ({one_hop_domain_url}) b/c of error: {e}"
                    )
                    self.excluded_domain_driver.add_excluded_domain(
                        ExcludedDomain(
                            domain_url=get_domain(one_hop_domain_url),
                            entity="Unknown",
                            alias_domains=[],
                            reason=OTHER_ERROR_REASON
                        )
                    )
        await self.crawler.close()
        

    async def ingest(self, url: str) -> Domain:        
        # * High-level logic
        # 1) Determine if we want to crawl this domain
        # - handle redirects, classify domain with LLM, check if domain or aliases already exist in ExcludedDomains or Domains table
        # 2) Request user confirmation
        # - requires the user's approval to proceed to the crawling step. if the user declines, the domain is added to the ExcludedDomains table
        # 3) Crawling
        # - crawl_domain() is invoked with timeout patience

        print(f"\nProcessing {url}...")

        domain = await self._validate_and_create_domain(url)

        # get user confirmation
        response = (
            input(
                f"\033[1;32mScraping: {domain.domain_url} — Press Y to scrape and anything else to skip & add to ExcludedDomains table (e.g. blacklist):\033[0m "
            )
            .strip()
            .upper()
        )
        if response != "Y":
            self.excluded_domain_driver.add_excluded_domain(
                domain=ExcludedDomain(
                    domain_url=domain.domain_url,
                    entity=domain.entity,
                    reason=NOT_A_BLOG_OR_PERSON_REASON,
                    alias_domains=[]
                )
            )
            raise SkipCrawlingDomainException(
                "User Input from CLI; Adding to ExcludedDomains table..."
            )

        # perform full crawl with retry logic; adds external/internal links to domain object
        await self._crawl_domain_with_retries(domain=domain)

        return domain

    async def _validate_and_create_domain(self, url: str) -> Domain:
        # sanitize URL
        url = sanitize_url(url)

        # pre-redirect URL
        pre_redirect_domain_url = get_domain(url)
        self._assert_domain_absent_in_db(pre_redirect_domain_url)

        # post-redirect URL
        crawler_res = await self._crawl_url(url=url)
        post_redirect_domain_url = get_domain(crawler_res.redirected_url)

        alias_url = None
        if post_redirect_domain_url != pre_redirect_domain_url:
            alias_url = pre_redirect_domain_url
            print_warn(f"Redirected from {pre_redirect_domain_url} to {post_redirect_domain_url}")
            self._assert_domain_absent_in_db(
                domain_url=post_redirect_domain_url, alias=pre_redirect_domain_url
            )

        # clasify domain to determine if we should pursue it
        domain_classifier_res = await self._classify_domain(
            url=url, cleaned_html=crawler_res.cleaned_html
        )

        def _is_valid_individual_blog(
            domain_classifier_res: ClassifyDomainAgentOutput,
        ) -> bool:
            return not domain_classifier_res.blog or domain_classifier_res.entity != "person"

        # if the url isn't a blog run by a person, add to ExcludedDomains table
        if _is_valid_individual_blog(domain_classifier_res):
            self.excluded_domain_driver.add_excluded_domain(
                domain=ExcludedDomain(
                    domain_url=post_redirect_domain_url,
                    entity=domain_classifier_res.entity,
                    alias_domains=[],
                    reason=NOT_A_BLOG_OR_PERSON_REASON,
                )
            )
            raise SkipCrawlingDomainException(
                "This domain isn't a blog run by an individual. Adding to ExcludedDomains table..."
            )

        # return a Domain object
        return Domain(
            domain_url=post_redirect_domain_url,
            entity=domain_classifier_res.entity,
            name=domain_classifier_res.name,
            alias_domains=[alias_url] if alias_url is not None else [],
            external_domains=[],
            target_internal_links=[],
            nontarget_internal_links=[],
            external_links=[],
            date_last_scraped=get_date_today(),
            entries=[],
        )

    async def _get_domain(self, url: str) -> Optional[Domain]:
        pre_redirect_domain_url = get_domain(url)
        if self.domain_driver.contains_domain(pre_redirect_domain_url):
            return self.domain_driver.get_domain(pre_redirect_domain_url)

        crawler_res = await self._crawl_url(url=url)
        post_redirect_domain_url = get_domain(crawler_res.redirected_url)

        if url != post_redirect_domain_url and self.domain_driver.contains_domain(post_redirect_domain_url):
            return self.domain_driver.get_domain(post_redirect_domain_url)
            
        raise Exception(f"Domain ({url}) not found.")

    def _assert_domain_absent_in_db(self, domain_url: str, alias: Optional[str] = None):
        if self.domain_driver.contains_domain(domain_url):
            if alias is not None:
                self.domain_driver.add_alias(domain_url=domain_url, alias=alias)
            raise SkipCrawlingDomainException(
                f"Skipping {domain_url} b/c it has already been scraped (it is present in the Domains table)"
            )
        elif self.excluded_domain_driver.contains_excluded_domain(domain_url):
            if alias is not None:
                self.excluded_domain_driver.add_alias(domain_url=domain_url, alias=alias)
            raise SkipCrawlingDomainException(
                f"Skipping {domain_url} b/c it is already present in the ExcludedDomains table"
            )

    async def _classify_domain(
        self, url: str, cleaned_html: str
    ) -> ClassifyDomainAgentOutput:
        domain_classifier_agent = ClassifyDomainAgent()
        domain_classifier_res = await domain_classifier_agent.async_call(
            url=url, html=cleaned_html
        )
        assert isinstance(domain_classifier_res.structured_output, ClassifyDomainAgentOutput)
        return domain_classifier_res.structured_output

    async def _crawl_domain_with_retries(self, domain: Domain):
        batch_size = BATCH_SIZE
        timeout_patience = 3
        while True:
            try:
                # crawl
                (
                    entries,
                    external_domains,
                    external_links,
                    target_internal_links,
                    nontarget_internal_links,
                ) = await self._crawl_domain(domain=domain, batch_size=BATCH_SIZE)

                # add domain to db
                print_ok(f"Adding domain ({domain.domain_url}) to DB")
                domain.external_domains = external_domains
                domain.external_links = external_links
                domain.target_internal_links = target_internal_links
                domain.nontarget_internal_links = nontarget_internal_links
                self.domain_driver.add_domain(domain)
                
                # add entries
                print_ok(f"Adding {len(entries)} entries to DB")
                self.entry_driver.add_entries(entries=entries)

                return
            except TooManyCrawlingTimeoutsException as e:
                batch_size = batch_size // 2
                print_warn(f"{str(e)}. Trying again with batch_size: {batch_size}.")
                timeout_patience -= 1
                if timeout_patience > 0:
                    continue
                self.excluded_domain_driver.add_excluded_domain(
                    domain=ExcludedDomain(
                        domain_url=domain.domain_url,
                        entity=domain.entity,
                        reason=TIMEOUT_ERROR_REASON,
                        alias_domains=[]
                    )
                )
                raise FatalException(
                    f"Could not scrape domain: {domain.domain_url} due to timeout issues"
                )
            except TooManyInternalLinks as e:
                self.excluded_domain_driver.add_excluded_domain(
                    domain=ExcludedDomain(
                        domain_url=domain.domain_url,
                        entity=domain.entity,
                        reason=TOO_MANY_INTERNAL_LINKS_REASON,
                        alias_domains=[]
                    )
                )
                raise FatalException(
                    f"Could not scrape domain: {domain.domain_url} due to error: {e}; Adding to ExcludedDomains table..."
                )
            except Exception as e:
                tb_str = traceback.format_exc()
                print_err(tb_str)
                self.excluded_domain_driver.add_excluded_domain(
                    domain=ExcludedDomain(
                        domain_url=domain.domain_url,
                        entity=domain.entity,
                        reason=OTHER_ERROR_REASON,
                        alias_domains=[]
                    )
                )
                raise FatalException(
                    f"Could not scrape domain: {domain.domain_url} due to error: {e}; Adding to ExcludedDomains table..."
                )

    @timing_decorator
    async def _crawl_domain(
        self, domain: Domain, batch_size: int
    ) -> Tuple[List[Entry], List[str], List[str], List[str], List[str]]:
        entries = []
        external_links: list[str] = []
        external_domains: list[str] = []
        target_internal_links: list[str] = []
        nontarget_internal_links: list[str] = []
        internal_links_queue: list[str] = [sanitize_url(domain.domain_url)]
        visited: dict[str, bool] = {}
        timeout_error_links: list[str] = []
        other_error_links: list[str] = []

        # BFS through all internal (same-domain) links in batches
        while True:
            batch_urls = []
            while internal_links_queue and len(batch_urls) < batch_size:
                internal_link = sanitize_url(internal_links_queue.pop(0))
                if internal_link not in visited and self._is_valid_internal_link(domain_url=domain.domain_url, url=internal_link):
                    batch_urls.append(internal_link)
                
            if not internal_links_queue and not batch_urls:
                break

            print("batch_urls", batch_urls, "\n")
            print("visited", visited, "\n")

            # run LLM to parse blog entry information form HTML
            tasks = [self._parse_url_to_entry(url=url, domain=domain, visited=visited) for url in batch_urls]

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

                # add current url & aliases to visited
                visited[entry.entry_url] = True
                for alias in entry.alias_urls:
                    visited[alias] = True

                new_external_domains_batch += [get_domain(link) for link in new_external_links]
                new_external_links_batch += [link for link in new_external_links]
                new_internal_links_batch += [link for link in new_internal_links]

            
            internal_links_queue = list(set(new_internal_links_batch + internal_links_queue))
            # internal_links_queue = [l for l in internal_links_queue if l not in visited]
            
            target_internal_links = list(set(new_target_links + target_internal_links))
            nontarget_internal_links = list(set(new_nontarget_links + nontarget_internal_links))
            external_links = list(set(new_external_links_batch + external_links))
            external_domains = list(set(new_external_domains_batch + external_domains))

            print(f"added {len(new_target_links)} blog posts: {new_target_links}")
            print(f"skipped {len(new_nontarget_links)} links: {new_nontarget_links}")

            print("# skipped links", len(nontarget_internal_links))
            print("# internal links", len(internal_links_queue))
            print("# external domains", len(external_domains))
            print("# visited", len(visited))

            # * If more than 20% of all crawls are timing out, then throw an error.
            if len(timeout_error_links) / len(visited) > 0.2:
                raise TooManyCrawlingTimeoutsException(
                    f"len(timeout_error_links) / len(visited) = {len(timeout_error_links) / len(visited)} > 0.2"
                )

            if len(internal_links_queue) > MAX_INTERNAL_LINKS_Q_SIZE:
                raise TooManyInternalLinks(f"{len(internal_links_queue)} links —— too many!")

        return (
            entries,
            external_domains,
            external_links,
            target_internal_links,
            nontarget_internal_links,
        )

    async def _parse_url_to_entry(self, url: str, domain: Domain, visited: Dict[str, bool]):
        print(f"Parsing {add_https_if_missing(url)}...")
        crawler_res = await self._crawl_url(url=url)
        post_redirect_url = crawler_res.redirected_url
        
        alias = None
        if url != post_redirect_url:
            print_warn(f"Redirected from {url} to {post_redirect_url}")
            if not self._is_valid_internal_link(domain_url=domain.domain_url, url=post_redirect_url):
                raise Exception(f"Link {url} redirected to {post_redirect_url} which is not in the same domain.")
            if post_redirect_url in visited:
                visited[url] = True
                print_warn(f"URL {url} redirected to {post_redirect_url} which was already visited")
                raise Exception(f"Link {url} redirected to {post_redirect_url} which has already been visited.")

        # grab internal / external links
        internal_links = [sanitize_url(link["href"])for link in crawler_res.links.get("internal", [])]
        external_links = [sanitize_url(link["href"]) for link in crawler_res.links.get("external", [])]

        # parse entry
        entry_parser = ParseEntryAgent()
        entry_parser_res = await entry_parser.async_call(url=post_redirect_url, html=crawler_res.cleaned_html)
        assert isinstance(entry_parser_res.structured_output, ParseEntryAgentOutput)
        parsed_entry = entry_parser_res.structured_output  # type: ignore

        # NOTE: PSQL doesn't like null bytes
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
            entry_url=sanitize_url(post_redirect_url),
            domain_url=domain.domain_url,
            alias_urls=[sanitize_url(alias)] if alias is not None else []
        )

        return parsed_entry.should_pursue, entry, internal_links, external_links


    async def _crawl_url(self, url: str) -> MyCrawlResult:
        # initial crawl
        try:
            url = add_https_if_missing(url)
            crawler_res = await self.crawler.arun(url=url, config=self.run_config)

            assert isinstance(crawler_res, CrawlResultContainer)
            assert len(crawler_res) == 1

            crawler_res = crawler_res._results[0]
            assert crawler_res.success
            assert crawler_res.redirected_url is not None
            assert crawler_res.cleaned_html is not None

            return MyCrawlResult(
                url=sanitize_url(crawler_res.url),
                success=crawler_res.success,
                redirected_url=sanitize_url(crawler_res.redirected_url),
                cleaned_html=crawler_res.cleaned_html,
                links=crawler_res.links
            )
        except Exception as e:
            raise FatalException(f"Crawling {url} failed with error: {str(e)}")

    def _is_valid_internal_link(self, domain_url: str, url: str) -> bool:
        return not is_id_or_static_resource(url) and is_from_same_domain_or_subdomain(url, domain_url)


if __name__ == "__main__":
    crawler = Crawler()
    asyncio.run(crawler.spider("https://thume.ca/"))

    # asyncio.run(spider("https://bigdanzblog.wordpress.com/"))
    # asyncio.run(spider("projects.drogon.net"))
    # asyncio.run(spider("filippo.io"))
