"""A cache hit returns evidence; the caller decides how to use it."""

from time import time

from app.shop.models import CacheEntry, ProductCard, TurnContext
from app.shop.reuse import AnswerReuse
from tests.test_shop_cache_flow import InMemoryCache, StubVerifier


def test_reuse_returns_product_evidence_without_changing_current_context() -> None:
    microphone = ProductCard(
        product_id="mic", title="Compact mic", description="For indoor interviews", url="/mic"
    )
    cached_context = TurnContext(message="Suggest an indoor mic", mode="both")
    cache = InMemoryCache()
    cache.entries.append(
        CacheEntry(
            scope="alex",
            mode="both",
            version="v1",
            question=cached_context.message,
            answer="Try the compact mic.",
            products=[microphone],
            context=cached_context,
            created_at=time(),
            expires_at=time() + 60,
        )
    )
    current = TurnContext(message="Which microphone for interviews indoors?", mode="both")
    before = current.model_copy(deep=True)
    reuse = AnswerReuse(cache, StubVerifier(), distance=0.2, confidence=0.5, ttl=60)

    result = reuse.find(current, "alex", "v1", lambda _: microphone)

    assert current == before
    assert result.answer is not None
    assert result.answer.text == "Try the compact mic."
    assert result.products == [microphone]
    assert result.trace.status == "hit"
