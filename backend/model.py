from dataclasses import dataclass

@dataclass
class Entry:
    blog: bool = False
    name: str = ""
    summary: str = ""
    topics: str = ""
    author: str = ""
    date: str = ""
    url: str = ""
    