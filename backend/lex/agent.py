from __future__ import annotations

from pydantic import BaseModel
from abc import ABC, abstractmethod
from typing import Callable, Optional

from .model import (
    LLMArgs,
    Summary,
    Exchange,
)

from .llm import LLM
from .parse import parse_response


class Agent(ABC):
    def __init__(
        self,
        llm: LLM,
        verbose: bool = False,
        structure: Optional[type[BaseModel]] = None,
        error_cb: Optional[Callable] = None,
    ):
        self.llm = llm
        self.name = self.__class__.__name__
        self.tags = []
        self.output_tag = ""
        self.llm_args = LLMArgs()
        self.verbose = verbose
        self.error_cb = error_cb
        self.structure = structure
        self.input_tokens = 0
        self.output_tokens = 0

    @abstractmethod
    def get_user_prompt(self, *args, **kwargs) -> str:
        pass

    @abstractmethod
    def get_system_prompt(self, *args, **kwargs) -> str:
        pass

    """ Default behavior for agent """

    def setup_call(self, **kwargs):
        user_prompt = self.get_user_prompt(**kwargs)
        system_prompt = self.get_system_prompt(**kwargs)
        return user_prompt, system_prompt, []

    def call(
        self,
        history: Optional[list[Exchange]] = None,
        image: Optional[str] = None,
        **kwargs,
    ) -> Summary:
        user_prompt, system_prompt, history = self.setup_call(**kwargs)
        response = self.llm.call(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            history=history if history is not None else [],
            llm_args=self.llm_args,
            image=image,
            structure=self.structure,
        )

        input_tokens, output_tokens = self.llm.usage(response)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

        if self.structure:
            summary = Summary(
                output=self.llm.structured(response),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        else:
            text = self.llm.text(response)
            parsed_response = parse_response(text, self.tags)
            output = parsed_response[self.output_tag] if self.output_tag else ""
            summary = Summary(
                output=output,
                log=parsed_response,
                raw=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        return summary

    async def async_call(
        self,
        history: Optional[list[Exchange]] = None,
        image: Optional[str] = None,
        **kwargs,
    ) -> Summary:
        user_prompt, system_prompt, history = self.setup_call(**kwargs)
        response = await self.llm.async_call(
            user_prompt=user_prompt,
            system_prompt=system_prompt,
            history=history if history is not None else [],
            llm_args=self.llm_args,
            image=image,
            structure=self.structure,
        )

        input_tokens, output_tokens = self.llm.usage(response)
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

        if self.structure:
            output = self.llm.structured(response)
            summary = Summary(
                output=output, input_tokens=input_tokens, output_tokens=output_tokens
            )
        else:
            text = self.llm.text(response)
            parsed_response = parse_response(text, self.tags)
            output = parsed_response[self.output_tag] if self.output_tag else ""
            summary = Summary(
                output=output,
                log=parsed_response,
                raw=text,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        return summary
