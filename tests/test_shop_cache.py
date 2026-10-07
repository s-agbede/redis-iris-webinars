"""Run with TEST_REDIS_URL against an isolated real Redis Search index."""

import os
from time import time
from uuid import uuid4

import pytest
from redis import Redis

from app.shop.cache import RedisAnswerCache
from app.shop.models import CacheEntry, TurnContext


class Encoder:
    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


@pytest.fixture
def cache():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("TEST_REDIS_URL enables real semantic-cache integration")
    client = Redis.from_url(url)
    cache = RedisAnswerCache(client, Encoder(), name=f"test-cache-{uuid4().hex}", distance=0.2)
    yield cache
    cache.backend.delete()
    client.close()


def entry(owner: str = "alex", **changes: object) -> CacheEntry:
    values = dict(
        scope=owner,
        version="v1",
        mode="both",
        question="Recommend a mic",
        answer="A compact microphone.",
        products=[],
        context=TurnContext(message="Recommend a mic", mode="both"),
        created_at=time(),
        expires_at=time() + 600,
    )
    values.update(changes)
    return CacheEntry.model_validate(values)


def test_identical_prompts_keep_separate_shopper_entries(cache):
    first, second = entry(), entry("jordan", answer="A studio microphone.")
    cache.store(first)
    cache.store(second)
    assert cache.lookup("A mic please", "alex", "both", "v1").entry.answer == first.answer
    assert cache.lookup("A mic please", "jordan", "both", "v1").entry.answer == second.answer
    assert cache.lookup("A mic please", "unknown", "both", "v1") is None


def test_mode_and_configuration_filter_before_search(cache):
    cache.store(entry())
    assert cache.lookup("A mic please", "alex", "none", "v1") is None
    assert cache.lookup("A mic please", "alex", "both", "v2") is None


def test_shared_entry_can_be_found_by_both_shoppers(cache):
    cache.store(entry("shared", mode="none"))
    assert cache.lookup("Explain aperture", "alex", "both", "v1").entry.scope == "shared"
    assert cache.lookup("Explain aperture", "jordan", "none", "v1").entry.scope == "shared"


def test_expired_payload_never_reused_even_when_redis_key_remains(cache):
    old = entry(created_at=time() - 50, expires_at=time() - 1)
    # Simulate stale data outliving logical expiry, independently of Redis TTL.
    cache.backend.store(
        prompt=old.question,
        response=old.model_dump_json(),
        filters=cache.filters(old),
        ttl=300,
    )
    assert cache.lookup(old.question, "alex", "both", "v1") is None


def test_delete_does_not_allow_foreign_owner_or_redis_keys(cache):
    original = entry()
    cache.store(original)
    assert not cache.remove(original.entry_id, "jordan")
    assert cache.lookup(original.question, "alex", "both", "v1") is not None
    assert cache.remove(original.entry_id, "alex")
    assert cache.lookup(original.question, "alex", "both", "v1") is None


def test_clear_only_selected_owner_preserves_shared_and_other_shopper(cache):
    for owner in ("alex", "jordan", "shared"):
        cache.store(entry(owner))
    assert cache.clear("alex") == 1
    assert cache.lookup("A mic", "jordan", "both", "v1").entry.scope in {"jordan", "shared"}


def test_malformed_cache_payload_fails_clearly(cache):
    original = entry()
    cache.backend.store(
        prompt=original.question,
        response="not json",
        filters=cache.filters(original),
        ttl=30,
    )
    from app.shop.cache import CacheError

    with pytest.raises(CacheError, match="invalid"):
        cache.lookup(original.question, "alex", "both", "v1")
