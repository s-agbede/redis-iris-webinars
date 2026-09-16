"""Shared product-to-vector preparation; callers own persistence and transactions."""

from collections.abc import Callable
from typing import Protocol

from tokenizers import Tokenizer

from app.catalog import make_passages
from app.models import CameraProduct, Passage
from app.settings import Settings


class PassageEncoder(Protocol):
    tokenizer: Tokenizer

    def embed_many(self, texts: list[str]) -> list[list[float]]: ...


class IndexedPassage(Passage):
    embedding: list[float]


def prepare_product_passages(
    product: CameraProduct | None,
    encoder: PassageEncoder,
    settings: Settings,
    *,
    reuse_embedding: Callable[[Passage], list[float] | None] | None = None,
) -> list[IndexedPassage]:
    """Build index records, optionally reusing verified same-model embeddings.

    A missing product produces no records, letting callers remove old passages.
    The optional lookup must check passage text and model compatibility before
    returning a vector. Missing vectors are embedded together in passage order.
    """
    if product is None:
        return []
    passages = make_passages(
        product, encoder.tokenizer, settings.passage_tokens, settings.passage_overlap
    )
    vectors = [reuse_embedding(p) if reuse_embedding else None for p in passages]
    missing = [i for i, vector in enumerate(vectors) if vector is None]
    if missing:
        generated = encoder.embed_many([passages[i].search_text for i in missing])
        for i, generated_vector in zip(missing, generated, strict=True):
            vectors[i] = generated_vector
    records = []
    for passage, vector in zip(passages, vectors, strict=True):
        assert vector is not None
        records.append(IndexedPassage(**passage.model_dump(), embedding=vector))
    return records
