import feedparser
from pprint import pprint

from agents.summarize import SummarizeBlogPost
from lex.llm import OpenAILLM

d = feedparser.parse("https://www.benkuhn.net/index.xml")

print(d.keys())

summarize_agent = SummarizeBlogPost(llm=OpenAILLM(model_name="gpt-4o"))

for e in d.entries:
    print(e.title)
    print(e.keys())
    print(e.description)
    print(e.summary)
    print(e.title_detail)
    print(e.links)
    print(e.link)
    print(e.published)

    print(summarize_agent.call(content=e.content))