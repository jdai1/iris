import os
from typing import TypeVar

from pydantic import BaseModel
from openai import AsyncOpenAI

T = TypeVar("T", bound=BaseModel)

_openai_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("PERSONAL_OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is not set (PERSONAL_OPENAI_API_KEY)")
        _openai_client = AsyncOpenAI(api_key=api_key)
    return _openai_client


T = TypeVar("T", bound=BaseModel)


async def extract_structured(
    prompt: str,
    output_model: type[T],
    system_prompt: str = "",
    model_name: str = "gpt-5-mini-2025-08-07",
    temperature: float = 0.0,
    max_completion_tokens: int = 4096,
    client: AsyncOpenAI | None = None,
) -> T:
    """
    Extract structured data from a prompt using an LLM

    Args:
        prompt: The user prompt
        output_model: Pydantic model class for structured output
        system_prompt: Optional system prompt
        model_name: OpenAI model name
        temperature: Sampling temperature
        max_tokens: Maximum tokens in response

    Returns:
        Instance of output_model with extracted structured data
    """
    client = client or _get_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = await client.beta.chat.completions.parse(
        model=model_name,
        messages=messages,
        response_format=output_model,
        max_completion_tokens=max_completion_tokens,
    )

    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("Failed to parse structured output from LLM response")

    return parsed
