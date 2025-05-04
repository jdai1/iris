import feedparser

d = feedparser.parse("https://pavelfatin.com/feed/")

for e in d.entries:
    print(e.title)
    # print(e.keys())
    # print(e.description)
    # print(e.summary)
    # print(e.title_detail)
    # print(e.links)
    # print(e.link)
    # print(e.published)