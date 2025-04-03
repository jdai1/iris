import os
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Tuple

from pydantic import BaseModel
from dotenv import load_dotenv
import anthropic
import openai

from .model import Exchange, LLMArgs, LLMAPIRetryException

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
async_anthropic_client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
async_openai_client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

"""
LLM Abstraction
"""


class LLM(ABC):
    error_count = 0
    query_count = 0

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @abstractmethod
    def get_message_history(self, history: list[Exchange]) -> list[dict]:
        pass

    @abstractmethod
    def setup_messages(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[Exchange],
        llm_args: LLMArgs,
        image: Optional[str] = None,
    ) -> list:
        pass

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[Exchange],
        llm_args: LLMArgs,
        image: Optional[str] = None,
        verbose: bool = False,
        structure: Optional[type[BaseModel]] = None,
    ) -> Any:
        pass

    @abstractmethod
    def async_call(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[Exchange],
        llm_args: LLMArgs,
        image: Optional[str] = None,
        verbose: bool = False,
        structure: Optional[type[BaseModel]] = None,
    ) -> Any:
        pass

    @abstractmethod
    def usage(self, response: Any) -> Tuple[int, int]:
        pass

    @abstractmethod
    def text(self, response: Any) -> str:
        pass

    @abstractmethod
    def structured(self, response: Any) -> dict:
        pass


class OpenAILLM(LLM):
    def __init__(self, model_name: str):
        self.model_name = model_name
        super().__init__(model_name=model_name)

    def get_message_history(self, history: list[Exchange]) -> list[dict]:
        message_history = []

        for response in history:
            message_history.append(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": response.query_text}],
                }
            )
            message_history.append(
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": response.response_text}],
                }
            )
        return message_history

    def setup_messages(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[Exchange],
        llm_args: LLMArgs,
        image: Optional[str] = None,
    ) -> list:
        messages = (
            self.get_message_history(history) if llm_args.populate_history else []
        )

        messages.insert(
            0, {"role": "system", "content": [{"type": "text", "text": system_prompt}]}
        )
        next_message = {
            "role": "user",
            "content": [{"type": "text", "text": user_prompt}],
        }

        if image is not None:
            next_message["content"].append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image}"},
                }
            )
        messages.append(next_message)
        return messages

    def exec_call_with_error_handling(
        self, f: Callable, llm_args: LLMArgs, *args, **kwargs
    ):
        try:
            return f(*args, **kwargs)
        except openai.APIStatusError as e:
            if (
                kwargs.get("llm_args")
                and e.status_code in kwargs["llm_args"].retry_config.on_status_codes
            ):
                raise LLMAPIRetryException(e.message, e.status_code)
            raise e
        except openai.APIError as e:
            raise LLMAPIRetryException(e.message, -1)

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[Exchange],
        llm_args: LLMArgs,
        image: Optional[str] = None,  # base64 encoded image
        verbose: bool = False,
        structure: Optional[type[BaseModel]] = None,
    ):
        messages = self.setup_messages(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            history=history,
            llm_args=llm_args,
            image=image,
        )
        assert not llm_args.stream
        if structure:
            return self.exec_call_with_error_handling(
                f=openai_client.beta.chat.completions.parse,
                llm_args=llm_args,
                model=self.model_name,
                max_tokens=llm_args.max_tokens,
                temperature=llm_args.temperature,
                messages=messages,  # type: ignore
                response_format=structure,
            )
        return self.exec_call_with_error_handling(
            f=openai_client.chat.completions.create,
            llm_args=llm_args,
            model=self.model_name,
            max_tokens=llm_args.max_tokens,
            temperature=llm_args.temperature,
            messages=messages,  # type: ignore
        )

    async def exec_call_async_with_error_handling(
        self, f: Callable, llm_args: LLMArgs, *args, **kwargs
    ):
        try:
            return await f(*args, **kwargs)
        except openai.APIStatusError as e:
            if (
                kwargs.get("llm_args")
                and e.status_code in kwargs["llm_args"].retry_config.on_status_codes
            ):
                raise LLMAPIRetryException(e.message, e.status_code)
            raise e
        except openai.APIError as e:
            raise LLMAPIRetryException(e.message, -1)

    async def async_call(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[Exchange],
        llm_args: LLMArgs,
        image: Optional[str] = None,  # base64 encoded image
        verbose: bool = False,
        structure: Optional[type[BaseModel]] = None,
    ):
        messages = self.setup_messages(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            history=history,
            llm_args=llm_args,
            image=image,
        )
        assert not llm_args.stream
        if structure:
            return await self.exec_call_async_with_error_handling(
                f=async_openai_client.beta.chat.completions.parse,
                llm_args=llm_args,
                model=self.model_name,
                max_tokens=llm_args.max_tokens,
                temperature=llm_args.temperature,
                messages=messages,  # type: ignore
                response_format=structure,
            )
        return await self.exec_call_async_with_error_handling(
            f=async_openai_client.chat.completions.create,
            llm_args=llm_args,
            model=self.model_name,
            max_tokens=llm_args.max_tokens,
            temperature=llm_args.temperature,
            messages=messages,  # type: ignore
        )

    def usage(self, response: openai.types.Completion):
        assert response.usage
        return response.usage.prompt_tokens, response.usage.completion_tokens

    def text(self, response: openai.types.Completion) -> str:
        return response.choices[0].message.content  # type: ignore

    def structured(self, response: openai.types.Completion) -> dict:
        return response.choices[0].message.parsed  # type: ignore
