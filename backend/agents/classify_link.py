from typing import Literal
from pydantic import BaseModel
from lex.agent import Agent
from lex.llm import LLM

class LinkClass(BaseModel):
    url: str
    entity: Literal["person", "company", "organization", "government", "school"]
    name: str
    blog: bool

class ClassifyLinkAgent(Agent):
    def __init__(self, llm: LLM, **kwargs):
        super().__init__(llm=llm, structure=LinkClass, **kwargs)

    def get_user_prompt(self, url: str, html: str):
        return f"""
        You're given the URL and HTML of a webpage. Your task is extract information about the webpage

        URL:
        {url}
        
        HTML: 
        {html}
        
        You've been provided the URL and HTML for a web page with content. Determine the following:
        - url: The URL
        - entity: The type of the entity represented by the website; if not readily obvious, it is likely an individual
        - name: The name of the entity
        - blog: Whether or not the webpage has consumable content in the form of blog posts
        """

    def get_system_prompt(self, url: str, html: str):
        return ""

