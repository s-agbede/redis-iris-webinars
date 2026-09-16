"""Live product records and durable change events in the same Redis transaction."""

import json
from collections.abc import Iterable
from typing import Any, TypedDict, cast

from redis import Redis
from redis.exceptions import ResponseError

from app.models import CameraProduct
from app.settings import Settings


class IndexTarget(TypedDict):
    name: str
    prefix: str
    count_key: str


class ProductStore:
    group = "passage-sync"

    def __init__(self, client: Redis, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.events_key = f"{settings.namespace}:changes"
        self.registry_key = f"{settings.namespace}:deploy"
        self.reset_key = f"{settings.namespace}:reset-products"
        self.titles_key = f"{settings.namespace}:demo-titles"
        self.count_key = f"{settings.namespace}:expected-passages"
        self.catalog_revision_key = f"{settings.namespace}:catalog-revision"
        self.demo_key = f"{settings.namespace}:demo-products"
        self.paused_key = f"{settings.namespace}:sync-paused"
        self.error_key = f"{settings.namespace}:sync-error"
        self.lock_key = f"{settings.namespace}:sync-lock"
        try:
            client.xgroup_create(self.events_key, self.group, id="0-0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def key(self, product_id: str) -> str:
        return f"{self.settings.product_prefix}:us:{product_id}"

    def revision_key(self, product_id: str) -> str:
        return f"{self.settings.namespace}:revision:{product_id}"

    def targets(self) -> list[IndexTarget]:
        raw = cast(bytes | None, self.client.get(self.registry_key))
        if raw is None:
            return [
                IndexTarget(
                    name=self.settings.products_index,
                    prefix=self.settings.passage_prefix,
                    count_key=self.count_key,
                )
            ]
        registry = json.loads(raw)
        targets: dict[str, IndexTarget] = {}
        for role in ("active", "candidate", "previous"):
            target = registry.get(role)
            if target:
                targets[target["name"]] = IndexTarget(
                    name=target["name"], prefix=target["prefix"], count_key=target["count_key"]
                )
        return list(targets.values())

    def passage_keys(self, product_id: str, prefix: str | None = None) -> list[str]:
        prefix = prefix or self.targets()[0]["prefix"]
        return [
            key.decode()
            for key in self.client.scan_iter(match=f"{prefix}:us:{product_id}:*", count=250)
        ]

    def passage_count(self, product_id: str) -> int:
        return len(self.passage_keys(product_id))

    def get_many(self, ids: Iterable[str]) -> dict[str, CameraProduct]:
        unique = list(dict.fromkeys(ids))
        if not unique:
            return {}
        pipe = self.client.pipeline(transaction=False)
        for pid in unique:
            pipe.json().get(self.key(pid))
        return {
            pid: CameraProduct.model_validate(raw)
            for pid, raw in zip(unique, pipe.execute(), strict=True)
            if raw is not None
        }

    def get(self, product_id: str) -> CameraProduct | None:
        return self.get_many([product_id]).get(product_id)

    def all(self) -> dict[str, CameraProduct]:
        keys = list(self.client.scan_iter(match=f"{self.settings.product_prefix}:us:*", count=500))
        products: dict[str, CameraProduct] = {}
        for offset in range(0, len(keys), 250):
            pipe = self.client.pipeline(transaction=False)
            for key in keys[offset : offset + 250]:
                pipe.json().get(key)
            for raw in pipe.execute():
                if raw is not None:
                    p = CameraProduct.model_validate(raw)
                    products[p.product_id] = p
        return products

    def save(self, product: CameraProduct, *, demo: bool = True) -> None:
        with self.client.pipeline(transaction=True) as pipe:
            pipe.json().set(self.key(product.product_id), "$", product.model_dump())
            pipe.incr(self.revision_key(product.product_id))
            pipe.incr(self.catalog_revision_key)
            if demo:
                pipe.sadd(self.demo_key, product.product_id)
                pipe.hset(self.titles_key, product.product_id, product.product_title)
            pipe.xadd(self.events_key, {"product_id": product.product_id})
            pipe.execute()

    def delete(self, product_id: str) -> None:
        with self.client.pipeline(transaction=True) as pipe:
            pipe.delete(self.key(product_id))
            pipe.incr(self.revision_key(product_id))
            pipe.incr(self.catalog_revision_key)
            pipe.xadd(self.events_key, {"product_id": product_id})
            pipe.execute()

    def reset(self) -> None:
        for pid in self.demo_ids():
            self.client.sadd(self.reset_key, pid)
            self.delete(pid)

    def demo_ids(self) -> list[str]:
        return sorted(pid.decode() for pid in self.client.sscan_iter(self.demo_key))

    def backlog(self) -> dict[str, int]:
        groups: Any = self.client.xinfo_groups(self.events_key)
        group = next(g for g in groups if g["name"] == self.group.encode())
        return {"unread": int(group.get("lag") or 0), "pending": int(group["pending"])}
