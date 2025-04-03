from pydantic import BaseModel
from lex.agent import Agent
from lex.llm import LLM

class ParsedEntry(BaseModel):
    blog: bool
    name: str
    summary: str
    topics: str
    author: str
    date: str

class ParseEntryAgent(Agent):
    def __init__(self, llm: LLM, **kwargs):
        super().__init__(llm=llm, structure=ParsedEntry, **kwargs)

    def get_user_prompt(self, url: str, html: str):
        return f"""
        You're given the HTML of a webpage. Your task is to parse the unstructured contents of the web page into a structured
        form to provide content to an RSS reader.

        URL:
        {url}
        
        HTML: 
        {html}
        
        You've been provided the HTML for a web page with content. Determine the following:
        - blog: Is the HTML representative of a standalone blog post? Only fill the remainder of the fields if your answer to this question is YES

        If the HTML is not representative of a blog, fill in the remaining fields with empty strings. Otherwise, proceed:
        - name: What is the title?
        - summary: Summarize the above content in two sentences. Be creative and try to capture the essence of the text. Does not have to be an objective summary, try to mimick the voice of the author as much as you can. Do not use `the author` or `I` as pronouns. Instead, speak directly to the reader.
        - topics: What are some key relevant topics? Output a comma separated list
        - author: Who wrote the article?
        - date: When was the article published? If unknown or invalid, leave empty.
        """

    def get_system_prompt(self, url: str, html: str):
        return ""

