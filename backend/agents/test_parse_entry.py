import asyncio

from ..crawl import Crawler
from parse_entry import ParseEntryAgent, ParseEntryAgentOutput

async def test(url: str):
    crawler = Crawler()
    crawler_res = await crawler._crawl_url(url)

    entry_parser = ParseEntryAgent()
    entry_parser_res = await entry_parser.async_call(url=crawler_res.redirected_url, html=crawler_res.cleaned_html)

    print(entry_parser_res)
    
asyncio.run(test("https://davepagurek.com/art/hourly-comics-25"))


