from typing import Sequence

from openai import AsyncOpenAI

from app.services.llm_platform import _get_client
from app.utils.logger import scraper_logger as logger

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536


async def generate_embedding(
    text: str, client: AsyncOpenAI | None = None
) -> list[float]:
    """
    Generate an embedding for a single text string.

    Args:
        text: The text to embed
        client: Optional OpenAI client (uses default if not provided)

    Returns:
        List of floats representing the embedding vector (1536 dimensions)

    Raises:
        Exception: If embedding generation fails
    """
    client = client or _get_client()

    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        embedding = response.data[0].embedding
        return embedding
    except Exception as e:
        logger.error(f"Failed to generate embedding: {str(e)}")
        raise


async def generate_embeddings_batch(
    texts: Sequence[str], client: AsyncOpenAI | None = None
) -> list[list[float]]:
    """
    Generate embeddings for multiple texts in a single batch API call.

    Args:
        texts: Sequence of texts to embed
        client: Optional OpenAI client (uses default if not provided)

    Returns:
        List of embedding vectors, one per input text

    Raises:
        Exception: If embedding generation fails
    """
    if not texts:
        return []

    client = client or _get_client()

    try:
        response = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=list(texts),
        )
        embeddings = [item.embedding for item in response.data]
        return embeddings
    except Exception as e:
        logger.error(f"Failed to generate embeddings batch: {str(e)}")
        raise
