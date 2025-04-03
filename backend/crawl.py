import asyncio
from pprint import pprint
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

from util import add_https_if_missing, timing_decorator, is_id_or_static_resource, get_domain
from agents.parse_entry import ParseEntryAgent, ParsedEntry
from agents.classify_link import ClassifyLinkAgent, LinkClass
from lex.llm import OpenAILLM
from db import add_entries, query_entries, add_link, query_links
from model import Entry


""" Crawls a URL via BFS: Returns all found blog posts, external domains, and externl links """


@timing_decorator
async def crawl(
    url: str, link: LinkClass, batch_size: int = 10
) -> tuple[list[Entry], list[str], list[str]]:
    rss = []
    browser_config = BrowserConfig()
    run_config = CrawlerRunConfig()

    internal_links: list[str] = [url]
    external_links: list[str] = []
    external_domains: list[str] = []
    visited: dict[str, bool] = {}
    entry_parser = ParseEntryAgent(llm=OpenAILLM(model_name="gpt-4o-mini"))

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # BFS through all internal (same-domain) links
        while internal_links:
            batch_urls = [
                link
                for link in internal_links[:batch_size]
                if urlparse(link).path not in visited
            ]
            internal_links = internal_links[batch_size:]

            # run LLM to parse blog entry information form HTML
            tasks = [
                parse_blog_entry(url, entry_parser, run_config, crawler)
                for url in batch_urls
            ]

            results = await asyncio.gather(*tasks)
            for res in results:
                current_url, entry, new_internal_links, new_external_links = res

                # only append to rss if entry is a blog
                if entry.blog:
                    rss.append(entry)

                internal_links += new_internal_links
                external_links += new_external_links

                new_external_links = [add_https_if_missing(link) for link in new_external_links]
                external_domains = list(set(new_external_links + external_domains))
                visited[urlparse(current_url).path] = True

    print("total input tokens:", entry_parser.input_tokens)
    print("total output_tokens:", entry_parser.output_tokens)

    return rss, external_domains, external_links


""" Parses a single URL into a Blog Entry """
async def parse_blog_entry(
    url: str,
    entry_parser: ParseEntryAgent,
    run_config: CrawlerRunConfig,
    crawler: AsyncWebCrawler,
):
    result = await crawler.arun(url=url, config=run_config)

    if not result.success:
        raise Exception("Something went wrong when scraping this URL:", url)

    internal_links = [
        link["href"]
        for link in result.links.get("internal", [])
        if not is_id_or_static_resource(link["href"])
    ]
    external_links = [link["href"] for link in result.links.get("external", [])]

    entry_parser_res = await entry_parser.async_call(url=url, html=result.cleaned_html)
    parsed_entry: ParsedEntry = entry_parser_res.output  # type: ignore

    entry = Entry(
        **parsed_entry.__dict__,
        url=url,
    )

    return url, entry, internal_links, external_links


""" Classify links to 1) determine if we should crawl them and 2) create corresponding nodes on our map """


async def parse_links(external_domains: list[str], batch_size: int = 50):
    browser_config = BrowserConfig()
    run_config = CrawlerRunConfig(page_timeout=5000)
    link_classifier = ClassifyLinkAgent(llm=OpenAILLM(model_name="gpt-4o-mini"))

    async def classify_single_link(
        url: str,
        link_classifier: ClassifyLinkAgent,
        run_config: CrawlerRunConfig,
        crawler: AsyncWebCrawler,
    ) -> LinkClass:
        url = add_https_if_missing(url)
        result = await crawler.arun(url=url, config=run_config)

        if not result.success:
            raise Exception("Something went wrong when scraping this URL:", url)

        link_classifier_res = await link_classifier.async_call(
            url=url, html=result.cleaned_html
        )
        link_class: LinkClass = link_classifier_res.output  # type: ignore
        pprint(link_class.__dict__)
        return link_class

    async with AsyncWebCrawler(config=browser_config) as crawler:
        while external_domains:
            batch_urls = external_domains[:batch_size]
            external_domains = external_domains[batch_size:]
            tasks = [
                classify_single_link(url, link_classifier, run_config, crawler)
                for url in batch_urls
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, BaseException):
                    continue
                add_link(
                    url=get_domain(res.url), entity=res.entity, name=res.name, blog=res.blog
                )


if __name__ == "__main__":
    asyncio.run(parse_links(external_domains=["benkuhn.net", "sriramk.com"]))

    links = query_links()

    for l in links:
        print(l)
    
    # res, domains, links = asyncio.run(crawl(url))

    # add_entries(entries=res)
    # query_entries()

    # pprint([r.__dict__ for r in res])

    # add_link(url=url, external_domains=domains, external_links=links)
    # query_links()

    # pprint(domains)
    # pprint(links)

    # external_domains_from_ben_kuhn = links[0].external_domains.split(",")

    # asyncio.run(classify(external_domains=["paulgraham.com/"]))

# input one link. probably want to have human in the loop way of choosing the next ones.
