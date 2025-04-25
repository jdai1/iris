from datetime import date
from pydantic import BaseModel
from lex.agent import Agent
from lex.llm import LLM, OpenAILLM

class ParseEntryAgentOutput(BaseModel):
    is_blog: bool
    title: str
    summary: str
    topics: list[str]
    author: str
    date_published: str

class ParseEntryAgent(Agent):
    def __init__(self, llm: LLM = OpenAILLM(model_name="gpt-4.1-mini-2025-04-14"), **kwargs):
        super().__init__(llm=llm, structure=ParseEntryAgentOutput, **kwargs)

    def get_user_prompt(self, url: str, html: str):
        return f"""
        You're given the HTML of a webpage. Your task is to parse the unstructured contents of the web page into a structured
        form to provide content to an RSS reader.

        URL:
        {url}
        
        HTML: 
        {html}

        A blog post should discuss a technical topic, provide advice, tell anecdotes, review a piece of media etc. In general, anything that presents an opinion on something (technical or not) should be classified as a blog post and processed.
        
        You've been provided the HTML for a web page with content. Determine the following:
        - is_blog: Is the HTML representative of a standalone blog post? Only fill the remainder of the fields if your answer to this question is YES

        If the HTML is not representative of a blog, fill in the remaining fields with empty strings. Otherwise, proceed:
        - name: What is the title?
        - summary: Summarize the above content in two sentences. Be creative and try to capture the essence of the text. Does not have to be an objective summary, try to mimick the voice of the author as much as you can. Do not use `the author` or `I` as pronouns. Instead, speak directly to the reader.
        - topics: What are some key relevant topics? Output a list of strings.
        - author: Who wrote the article?
        - date_published: When was the article published? If unknown or invalid, leave empty. Make sure that if you output a date, that it is in the format "YYYY-MM-DD".
        """

    def get_system_prompt(self, url: str, html: str):
        return ""

