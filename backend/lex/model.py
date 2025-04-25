from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel


@dataclass
class Exchange:
    query_text: str
    response_text: str


@dataclass
class LLMArgs:
    stream: bool = False
    temperature: float = 0
    populate_history: bool = False
    max_tokens: int = 4096


@dataclass
class Summary():
    output: Optional[str] = None
    structured_output: Optional[BaseModel] = None  # structured output (if applicable)
    log: dict = field(default_factory=dict)
    raw: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    system_prompt: str = ""
    user_prompt: str = ""
    model_name: str = ""


class RetryException(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class LLMAPIRetryException(RetryException):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class ParsingRetryException(RetryException):
    def __init__(self, message: str, text: str, tag: str):
        super().__init__(message)
        self.text = text
        self.tag = tag
        self.message = message
