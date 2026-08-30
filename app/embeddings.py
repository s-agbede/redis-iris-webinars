"""Query and document embedding.

Hosted OpenAI embeddings rather than a local model, for three reasons:
the agent already requires an OpenAI key so local buys no key-free setup;
`sentence-transformers` drags in torch (~2GB), which breaks the promise that
this repo clones and runs quickly; and per-query cost is a rounding error.

The tradeoff is a network hop on every search, visible as `embed_ms` in the
receipt. We leave it visible rather than hiding it.
"""

from __future__ import annotations

from redisvl.extensions.cache.embeddings import EmbeddingsCache
from redisvl.utils.vectorize import OpenAITextVectorizer

from app.settings import Settings


def build_vectorizer(settings: Settings) -> OpenAITextVectorizer:
    """Construct the vectorizer, optionally backed by a Redis embeddings cache.

    The cache means a repeated query skips the OpenAI call and drops `embed_ms`
    to near zero — a small preview of the argument episode 4 makes at the scale
    of whole LLM responses.
    """
    cache = (
        EmbeddingsCache(name="embedcache", redis_url=settings.redis_url)
        if settings.embedding_cache_enabled
        else None
    )
    return OpenAITextVectorizer(
        model=settings.embedding_model,
        api_config={"api_key": settings.openai_api_key},
        cache=cache,
    )
