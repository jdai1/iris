from typing import Literal
from pydantic import BaseModel
from lex.agent import Agent
from lex.llm import LLM, OpenAILLM

class ClassifyDomainAgentOutput(BaseModel):
    url: str
    entity: Literal["person", "company", "organization", "government", "school"]
    name: str
    blog: bool

class ClassifyDomainAgent(Agent):
    def __init__(self, llm: LLM = OpenAILLM(model_name="gpt-4.1-mini-2025-04-14"), **kwargs):
        super().__init__(llm=llm, structure=ClassifyDomainAgentOutput, **kwargs)


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
        - name: The name of the entity that is writing. If none is present, output "NONE"
        - blog: Whether or not the website is a blog
        """

    def get_system_prompt(self, url: str, html: str):
        return ""

