from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


BACKEND_DIR = Path(__file__).resolve().parents[3]
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")


def database_url() -> str:
    return os.getenv("DATABASE_URL") or os.getenv("DEV_DATABASE_URL") or f"sqlite:///{BACKEND_DIR / 'iris.db'}"


USER_AGENT = os.getenv(
    "IRIS_USER_AGENT",
    "IrisBot/0.1 (+local personal research crawler)",
)

REQUEST_TIMEOUT_SECONDS = float(os.getenv("IRIS_REQUEST_TIMEOUT_SECONDS", "12"))
MAX_HTML_BYTES = int(os.getenv("IRIS_MAX_HTML_BYTES", "3000000"))
DEFAULT_MAX_PAGES = int(os.getenv("IRIS_DEFAULT_MAX_PAGES", "80"))
DEFAULT_MAX_DEPTH = int(os.getenv("IRIS_DEFAULT_MAX_DEPTH", "3"))
SOURCE_CLASSIFIER_MODEL = os.getenv("IRIS_SOURCE_CLASSIFIER_MODEL", "gpt-5-nano-2025-08-07")
SOURCE_CLASSIFIER_TIMEOUT_SECONDS = float(os.getenv("IRIS_SOURCE_CLASSIFIER_TIMEOUT_SECONDS", "20"))
DOCUMENT_CLASSIFIER_MODEL = os.getenv("IRIS_DOCUMENT_CLASSIFIER_MODEL", "gpt-5-nano-2025-08-07")
DOCUMENT_CLASSIFIER_TIMEOUT_SECONDS = float(os.getenv("IRIS_DOCUMENT_CLASSIFIER_TIMEOUT_SECONDS", "20"))
EMBEDDING_MODEL = os.getenv("IRIS_EMBEDDING_MODEL", "text-embedding-3-small")
USE_OPENAI_EMBEDDINGS = os.getenv("IRIS_USE_OPENAI_EMBEDDINGS", "0").lower() in {"1", "true", "yes"}
EMBEDDING_TIMEOUT_SECONDS = float(os.getenv("IRIS_EMBEDDING_TIMEOUT_SECONDS", "20"))
SEARCH_RERANK_MODEL = os.getenv("IRIS_SEARCH_RERANK_MODEL", "gpt-5-nano-2025-08-07")
USE_LLM_RERANKER = os.getenv("IRIS_USE_LLM_RERANKER", "0").lower() in {"1", "true", "yes"}
SEARCH_RERANK_TIMEOUT_SECONDS = float(os.getenv("IRIS_SEARCH_RERANK_TIMEOUT_SECONDS", "25"))
AGENT_SEARCH_MODEL = os.getenv("IRIS_AGENT_SEARCH_MODEL", "gpt-5.4-mini")
AGENT_SEARCH_MAX_TURNS = int(os.getenv("IRIS_AGENT_SEARCH_MAX_TURNS", "8"))
SOURCE_PROFILE_MODEL = os.getenv("IRIS_SOURCE_PROFILE_MODEL", "gpt-5.4-mini")
SOURCE_PROFILE_TIMEOUT_SECONDS = float(os.getenv("IRIS_SOURCE_PROFILE_TIMEOUT_SECONDS", "45"))


class MissingOpenAIKeyError(RuntimeError):
    pass


def openai_api_key() -> str | None:
    for name in ("OPENAI_API_KEY", "PERSONAL_OPENAI_API_KEY", "OPENAI_PERSONAL_API_KEY"):
        value = os.getenv(name)
        if value:
            return value

    env_file = os.getenv("IRIS_OPENAI_ENV_FILE")
    candidate_paths = [Path(env_file)] if env_file else []
    candidate_paths.extend(
        [
            Path.home() / "Desktop" / "random shit" / "env",
            Path.home() / ".env",
        ]
    )
    for path in candidate_paths:
        if not path.exists():
            continue
        values = dotenv_values(path)
        for name in ("OPENAI_API_KEY", "PERSONAL_OPENAI_API_KEY", "OPENAI_PERSONAL_API_KEY"):
            value = values.get(name)
            if value:
                return value
    return None


def require_openai_api_key(feature: str) -> str:
    key = openai_api_key()
    if key:
        return key
    raise MissingOpenAIKeyError(
        f"OpenAI API key is required for {feature}. Set OPENAI_API_KEY, "
        "PERSONAL_OPENAI_API_KEY, OPENAI_PERSONAL_API_KEY, or IRIS_OPENAI_ENV_FILE."
    )
