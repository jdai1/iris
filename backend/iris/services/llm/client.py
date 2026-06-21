from __future__ import annotations

import json
import re

import httpx

from iris.schemas.enums import LLMProvider
from iris.services.common.config import DEEPSEEK_API_BASE, require_deepseek_api_key, require_openai_api_key


def generate_json(
    *,
    provider: LLMProvider,
    model: str,
    instructions: str,
    input_payload: dict,
    schema: dict[str, object],
    timeout_seconds: float,
    max_tokens: int = 3500,
) -> dict:
    """Generate one JSON object through the configured LLM provider."""
    if provider == LLMProvider.OPENAI:
        return generate_openai_json(
            api_key=require_openai_api_key("LLM JSON generation"),
            model=model,
            instructions=instructions,
            input_payload=input_payload,
            schema=schema,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    if provider == LLMProvider.DEEPSEEK:
        return generate_deepseek_json(
            api_key=require_deepseek_api_key("LLM JSON generation"),
            model=model,
            instructions=instructions,
            input_payload=input_payload,
            schema=schema,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
        )
    raise ValueError(f"unsupported LLM provider: {provider}")


def generate_openai_json(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_payload: dict,
    schema: dict[str, object],
    timeout_seconds: float,
    max_tokens: int,
) -> dict:
    payload = {
        "model": model,
        "instructions": instructions,
        "input": json.dumps(input_payload, ensure_ascii=False),
        "text": {"format": schema, "verbosity": "low"},
        "reasoning": {"effort": "low"},
        "max_output_tokens": max_tokens,
        "store": False,
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"OpenAI JSON generation failed: {response.text[:1000]}") from exc
        data = response.json()
    text = data.get("output_text") or response_output_text(data)
    if not text:
        raise ValueError("empty OpenAI JSON response")
    return parse_json_object(text)


def generate_deepseek_json(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_payload: dict,
    schema: dict[str, object],
    timeout_seconds: float,
    max_tokens: int,
) -> dict:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"{instructions} Return only valid JSON. "
                    f"The JSON object must match this schema: {json.dumps(schema.get('schema', schema), ensure_ascii=False)}"
                ),
            },
            {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            f"{DEEPSEEK_API_BASE.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"DeepSeek JSON generation failed: {response.text[:1000]}") from exc
        data = response.json()
    text = ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
    if not text:
        raise ValueError("empty DeepSeek JSON response")
    return parse_json_object(text)


def parse_json_object(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        start = clean.find("{")
        end = clean.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(clean[start : end + 1])


def response_output_text(data: dict) -> str:
    """Extract Responses API output text."""
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") == "output_text" and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)
