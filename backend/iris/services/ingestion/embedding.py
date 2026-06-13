from __future__ import annotations

import hashlib
import json
import math
import re

import httpx

from iris.services.common.config import EMBEDDING_MODEL, EMBEDDING_TIMEOUT_SECONDS, USE_OPENAI_EMBEDDINGS, openai_api_key


DIMENSIONS = 96
MAX_EMBED_TEXT_CHARS = 8000
EMBED_BODY_CHARS = 5000


def embed_text(text: str, *, prefer_openai: bool | None = None) -> list[float]:
    use_openai = prefer_openai if prefer_openai is not None else USE_OPENAI_EMBEDDINGS
    if use_openai:
        vector = _embed_openai(text)
        if vector is not None:
            return vector
    return embed_text_local(text)


async def embed_text_async(text: str, *, prefer_openai: bool | None = None) -> list[float]:
    """Embed text using async HTTP when OpenAI embeddings are enabled."""
    use_openai = prefer_openai if prefer_openai is not None else USE_OPENAI_EMBEDDINGS
    if use_openai:
        vector = await _embed_openai_async(text)
        if vector is not None:
            return vector
    return embed_text_local(text)


def document_embedding_text(
    *,
    title: str | None,
    summary: str | None,
    topics: list[str] | None,
    extracted_text: str | None,
) -> str:
    """Build canonical document text for embeddings, including weighted topics."""
    clean_topics = [topic.strip() for topic in topics or [] if topic and topic.strip()]
    topic_text = "; ".join(clean_topics)
    parts = [
        f"Title: {title or ''}",
        f"Topics: {topic_text}",
        f"Topics: {topic_text}",
        f"Summary: {summary or ''}",
        f"Text: {(extracted_text or '')[:EMBED_BODY_CHARS]}",
    ]
    return "\n".join(parts)


def embed_text_local(text: str) -> list[float]:
    vector = [0.0] * DIMENSIONS
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9\-]{2,}", text.lower())
    for word in words:
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % DIMENSIONS
        sign = 1 if digest[4] % 2 == 0 else -1
        vector[idx] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _embed_openai(text: str) -> list[float] | None:
    key = openai_api_key()
    if not key:
        return None
    payload = {
        "model": EMBEDDING_MODEL,
        "input": text[:MAX_EMBED_TEXT_CHARS],
    }
    try:
        with httpx.Client(timeout=EMBEDDING_TIMEOUT_SECONDS) as client:
            response = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        values = response.json()["data"][0]["embedding"]
        norm = math.sqrt(sum(float(value) * float(value) for value in values)) or 1.0
        return [float(value) / norm for value in values]
    except Exception:
        return None


async def _embed_openai_async(text: str) -> list[float] | None:
    key = openai_api_key()
    if not key:
        return None
    payload = {
        "model": EMBEDDING_MODEL,
        "input": text[:MAX_EMBED_TEXT_CHARS],
    }
    try:
        async with httpx.AsyncClient(timeout=EMBEDDING_TIMEOUT_SECONDS) as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
        values = response.json()["data"][0]["embedding"]
        norm = math.sqrt(sum(float(value) * float(value) for value in values)) or 1.0
        return [float(value) / norm for value in values]
    except Exception:
        return None


def dumps_embedding(vector: list[float]) -> str:
    return json.dumps([round(value, 6) for value in vector])


def loads_embedding(value: str | None) -> list[float]:
    if not value:
        return [0.0] * DIMENSIONS
    loaded = json.loads(value)
    return [float(item) for item in loaded]


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(left * right for left, right in zip(a, b))
