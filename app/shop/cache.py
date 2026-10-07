"""Scoped RedisVL answer storage; the service owns admission and verification."""

from collections.abc import Iterator
from contextlib import contextmanager
from math import ceil
from time import time
from typing import Protocol

from pydantic import ValidationError
from redis import Redis
from redis.exceptions import RedisError
from redisvl.exceptions import RedisVLError
from redisvl.extensions.cache.llm import SemanticCache
from redisvl.query import FilterQuery
from redisvl.query.filter import Tag
from redisvl.utils.vectorize import CustomVectorizer

from app.shop.models import CacheCandidate, CacheEntry, MemoryMode


class CacheError(RuntimeError):
    """Safe cache error; ordinary generation can continue."""


class Encoder(Protocol):
    def embed(self, text: str) -> list[float]: ...


class AnswerCache(Protocol):
    def lookup(
        self, question: str, owner: str, mode: MemoryMode, version: str
    ) -> CacheCandidate | None: ...
    def store(self, entry: CacheEntry) -> str: ...
    def remove(self, entry_id: str, owner: str) -> bool: ...
    def clear(self, owner: str) -> int: ...


@contextmanager
def _cache_errors() -> Iterator[None]:
    try:
        yield
    except (RedisError, RedisVLError, ValueError, TypeError, KeyError):
        raise CacheError("Semantic cache is unavailable or returned invalid data.") from None


class RedisAnswerCache:
    def __init__(self, client: Redis, encoder: Encoder, *, name: str, distance: float) -> None:
        self.client, self.encoder, self.name, self.distance = client, encoder, name, distance
        self._backend: SemanticCache | None = None

    @property
    def backend(self) -> SemanticCache:
        # Lazy creation keeps cache outages from preventing ordinary chat startup.
        if self._backend is None:
            with _cache_errors():
                self._backend = SemanticCache(
                    name=self.name,
                    redis_client=self.client,
                    vectorizer=CustomVectorizer(embed=self.encoder.embed),
                    distance_threshold=self.distance,
                    # Per-entry TTL only: check() must not refresh a global TTL.
                    ttl=None,
                    filterable_fields=[
                        {"name": name, "type": "tag"}
                        for name in ("scope", "mode", "version", "entry_token")
                    ],
                )
        return self._backend

    @staticmethod
    def filters(entry: CacheEntry) -> dict[str, str]:
        return {
            "scope": entry.scope,
            "mode": entry.mode,
            "version": entry.version,
            "entry_token": entry.entry_id,
        }

    def lookup(
        self, question: str, owner: str, mode: MemoryMode, version: str
    ) -> CacheCandidate | None:
        with _cache_errors():
            allowed = ((Tag("scope") == owner) & (Tag("mode") == mode)) | (Tag("scope") == "shared")
            matches = self.backend.check(
                prompt=question,
                num_results=3,
                filter_expression=allowed & (Tag("version") == version),
            )
            for match in matches:
                try:
                    entry = CacheEntry.model_validate_json(match["response"])
                except ValidationError:
                    raise CacheError("Semantic cache returned an invalid answer payload.") from None
                # Recheck the payload before exposing any candidate metadata.
                if entry.scope not in (owner, "shared") or entry.version != version:
                    raise CacheError("Semantic cache returned an invalid scope.")
                if entry.scope != "shared" and entry.mode != mode:
                    raise CacheError("Semantic cache returned an invalid memory mode.")
                if entry.expires_at <= time():
                    self.remove(entry.entry_id, entry.scope)
                    continue
                return CacheCandidate(entry=entry, distance=max(0, match["vector_distance"]))
            return None

    def store(self, entry: CacheEntry) -> str:
        with _cache_errors():
            ttl = ceil(entry.expires_at - time())
            if ttl <= 0:
                raise CacheError("Cannot store an expired answer.")
            self.backend.store(
                prompt=entry.question,
                response=entry.model_dump_json(),
                filters=self.filters(entry),
                ttl=ttl,
            )
        return entry.entry_id

    def remove(self, entry_id: str, owner: str) -> bool:
        with _cache_errors():
            rows = self.backend.index.query(
                FilterQuery(
                    filter_expression=(Tag("entry_token") == entry_id) & (Tag("scope") == owner),
                    return_fields=["entry_token"],
                    num_results=1,
                )
            )
            if not rows:
                return False
            self.backend.drop(keys=[rows[0]["id"]])
            return True

    def clear(self, owner: str) -> int:
        deleted = 0
        with _cache_errors():
            while rows := self.backend.index.query(
                FilterQuery(
                    filter_expression=Tag("scope") == owner,
                    return_fields=["entry_token"],
                    num_results=100,
                )
            ):
                self.backend.drop(keys=[row["id"] for row in rows])
                deleted += len(rows)
        return deleted
