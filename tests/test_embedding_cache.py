from app.embedding_cache import EmbeddingCache


def test_cache_reuses_only_same_model_and_exact_query() -> None:
    calls: list[str] = []

    def embed(query: str) -> list[float]:
        calls.append(query)
        return [float(len(query))]

    cache = EmbeddingCache(capacity=2)
    assert cache.get("v1", "Sony", embed) == [4.0]
    cache.get("v1", "Sony", embed)
    cache.get("v2", "Sony", embed)
    cache.get("v2", "sony", embed)
    cache.get("v1", "Sony", embed)
    assert calls == ["Sony", "Sony", "sony", "Sony"]
