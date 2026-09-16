"""Persistent retry budgets and inspectable failed synchronization events."""

import time
from typing import Any, cast

from pydantic import BaseModel
from redis.exceptions import WatchError

from app.product_store import ProductStore


class FailedEvent(BaseModel):
    event_id: str
    original_event_id: str
    product_id: str
    error: str
    attempts: int


class SyncFailures:
    def __init__(self, store: ProductStore) -> None:
        self.store = store
        self.key = f"{store.settings.namespace}:changes:failed"
        self.attempts_key = f"{store.settings.namespace}:changes:attempts"
        self.retry_at_key = f"{store.settings.namespace}:changes:retry-at"

    def ready(self, event_id: bytes) -> bool:
        retry_at = cast(float | None, self.store.client.zscore(self.retry_at_key, event_id))
        return retry_at is None or retry_at <= time.time()

    def record(
        self,
        event_id: bytes,
        product_id: str,
        error: Exception,
        *,
        max_attempts: int,
        base_seconds: float,
    ) -> None:
        """Persist backoff, or transfer an exhausted event to the failed stream."""
        client = self.store.client
        attempts = cast(int, client.hincrby(self.attempts_key, event_id.decode(), 1))
        message = f"{type(error).__name__}: {error}"[:2000]
        with client.pipeline(transaction=True) as pipe:
            pipe.set(self.store.error_key, message)
            if attempts >= max_attempts:
                pipe.xadd(
                    self.key,
                    {
                        "original_event_id": event_id,
                        "product_id": product_id,
                        "error": message,
                        "attempts": attempts,
                    },
                )
                pipe.xack(self.store.events_key, self.store.group, event_id)
                self.clear(pipe, event_id)
            else:
                delay = min(60.0, base_seconds * 2 ** (attempts - 1))
                pipe.zadd(self.retry_at_key, {event_id: time.time() + delay})
            pipe.execute()

    def clear(self, pipeline: Any, event_id: bytes) -> None:
        pipeline.hdel(self.attempts_key, event_id)
        pipeline.zrem(self.retry_at_key, event_id)

    def count(self) -> int:
        return cast(int, self.store.client.xlen(self.key))

    def list(self) -> list[FailedEvent]:
        rows = cast(
            list[tuple[bytes, dict[bytes, bytes]]], self.store.client.xrevrange(self.key, count=50)
        )
        return [
            FailedEvent.model_validate(
                {
                    "event_id": event_id.decode(),
                    **{key.decode(): value.decode() for key, value in fields.items()},
                }
            )
            for event_id, fields in rows
        ]

    def retry(self, event_id: str) -> None:
        """Requeue the product's current state once; concurrent retries cannot duplicate it."""
        with self.store.client.pipeline() as pipe:
            try:
                pipe.watch(self.key)  # type: ignore[no-untyped-call]
                rows = pipe.xrange(self.key, min=event_id, max=event_id)
                if not rows:
                    raise ValueError("Failed event no longer exists. Refresh the panel.")
                fields = cast(Any, rows)[0][1]
                pipe.multi()
                pipe.xadd(self.store.events_key, {"product_id": fields[b"product_id"]})
                pipe.xdel(self.key, event_id)
                pipe.execute()
            except WatchError as exc:
                raise ValueError("Failure list changed. Refresh and retry.") from exc
