"""One small Stream consumer: fetch current state, derive passages, commit, acknowledge."""

import logging
from threading import Event, Thread
from typing import Any
from uuid import uuid4

from redis.exceptions import ConnectionError, LockError, RedisError, TimeoutError, WatchError
from redisvl.index import SearchIndex

from app.failures import SyncFailures
from app.indexing import PassageEncoder, prepare_product_passages
from app.product_store import ProductStore

logger = logging.getLogger(__name__)


class SyncWorker:
    def __init__(self, store: ProductStore, encoder: PassageEncoder, index: SearchIndex) -> None:
        self.store = store
        self.encoder = encoder
        self.index = index
        self.consumer = f"worker-{uuid4().hex}"
        self.stopping = Event()
        self.thread: Thread | None = None
        self.failures = SyncFailures(store)
        self.retry_base_seconds = 5.0
        self.max_attempts = 3
        self.claim_cursor = "0-0"

    def pause(self, paused: bool) -> None:
        self.store.client.set(self.store.paused_key, "1" if paused else "0")
        if paused:
            # Return only after an in-flight job completes, so the demo has a firm boundary.
            with self.store.client.lock(self.store.lock_key, timeout=60, blocking_timeout=30):
                pass

    def process_one(self, *, reclaim_idle_ms: int = 5000) -> bool:
        client = self.store.client
        lock = client.lock(self.store.lock_key, timeout=60, blocking=False)
        if not lock.acquire():
            return False
        event_id: bytes | None = None
        pid = ""
        try:
            if client.get(self.store.paused_key) == b"1":
                return False
            claimed: Any = client.xautoclaim(
                self.store.events_key,
                self.store.group,
                self.consumer,
                reclaim_idle_ms,
                start_id=self.claim_cursor,
                count=10,
            )
            self.claim_cursor = claimed[0].decode()
            messages = [row for row in claimed[1] if self.failures.ready(row[0])]
            if not messages:
                batches: Any = client.xreadgroup(
                    self.store.group, self.consumer, {self.store.events_key: ">"}, count=1
                )
                messages = batches[0][1] if batches else []
            if not messages:
                return False
            event_id, payload = messages[0]
            pid = payload[b"product_id"].decode()
            with client.pipeline() as pipe:
                # A concurrent update, delete, or expired ownership invalidates this write.
                pipe.watch(  # type: ignore[no-untyped-call]
                    self.store.revision_key(pid), self.store.key(pid), self.store.lock_key
                )
                product = self.store.get(pid)
                passages = prepare_product_passages(product, self.encoder, self.store.settings)
                targets = [
                    (target, self.store.passage_keys(pid, target["prefix"]))
                    for target in self.store.targets()
                ]
                if not lock.owned():
                    raise RuntimeError("Synchronization lease expired; event remains pending.")
                pipe.multi()
                for target, old_keys in targets:
                    if old_keys:
                        pipe.delete(*old_keys)
                    for p in passages:
                        pipe.json().set(
                            f"{target['prefix']}:{p.passage_id}",
                            "$",
                            p.model_dump(),
                        )
                    pipe.incrby(target["count_key"], len(passages) - len(old_keys))
                if product is None and client.sismember(self.store.reset_key, pid):
                    pipe.srem(self.store.demo_key, pid)
                    pipe.srem(self.store.reset_key, pid)
                    pipe.hdel(self.store.titles_key, pid)
                pipe.xack(self.store.events_key, self.store.group, event_id)
                self.failures.clear(pipe, event_id)
                pipe.delete(self.store.error_key)
                pipe.execute()
            return True
        except WatchError:
            # Current state changed during embedding; retry the pending event later.
            return True
        except (ConnectionError, TimeoutError, LockError):
            # Infrastructure failures must not exhaust a product's retry budget.
            raise
        except Exception as exc:
            if event_id is None or not lock.owned():
                raise
            logger.exception("Product synchronization failed: %s", pid)
            self.failures.record(
                event_id,
                pid,
                exc,
                max_attempts=self.max_attempts,
                base_seconds=self.retry_base_seconds,
            )
            return True
        finally:
            try:
                lock.release()
            except LockError:
                logger.warning("Synchronization ownership expired; pending work will be recovered.")

    def run(self) -> None:
        connection_delay = 1.0
        while not self.stopping.is_set():
            try:
                worked = self.process_one()
                connection_delay = 1.0
            except (ConnectionError, TimeoutError):
                logger.exception("Redis unavailable; keeping events for recovery")
                self.stopping.wait(connection_delay)
                connection_delay = min(30.0, connection_delay * 2)
                continue
            except (RedisError, RuntimeError, ValueError, KeyError) as exc:
                logger.exception("Passage synchronization failed")
                try:
                    self.store.client.set(self.store.error_key, str(exc))
                except RedisError:
                    logger.exception("Could not record synchronization error")
                worked = False
            if not worked:
                self.stopping.wait(0.25)

    def start(self) -> None:
        self.thread = Thread(target=self.run, name="passage-sync", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stopping.set()
        if self.thread:
            self.thread.join(timeout=30)
