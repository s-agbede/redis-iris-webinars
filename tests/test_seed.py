import json
import os
from contextlib import contextmanager, nullcontext
from typing import Any
from uuid import uuid4

import pytest
from redis import Redis
from redisvl.index import SearchIndex

from app.catalog import Catalog
from app.product_store import ProductStore
from app.search import index_identity
from app.settings import Settings
from app.sync import SyncWorker
from seed.load import current_manifest, load
from tests.test_catalog import product, tokenizer
from tests.test_search import service


class RedisSnapshot:
    def __init__(
        self, manifest: dict[str, Any], count: int, *, values: dict[str, bytes] | None = None
    ) -> None:
        self.manifest = manifest
        self.count = count
        self.values = values or {}
        self.searched_index: str | None = None

    def get(self, key: str) -> bytes | None:
        if key.endswith(":manifest"):
            return json.dumps(self.manifest).encode()
        return self.values.get(key)

    def execute_command(self, *args: str) -> list[object]:
        self.searched_index = args[1]
        return [b"num_docs", self.count, b"indexing", 0]

    def lock(self, *args, **kwargs):
        return nullcontext()


def test_only_reuse_a_complete_index_of_the_same_data_and_model() -> None:
    settings = Settings(_env_file=None)
    catalog = Catalog.load(settings.data_dir)
    manifest = {**index_identity(settings, catalog), "passage_count": 123}
    assert current_manifest(RedisSnapshot(manifest, 123), settings, catalog) == manifest
    assert current_manifest(RedisSnapshot(manifest, 122), settings, catalog) is None
    assert (
        current_manifest(
            RedisSnapshot({**manifest, "embedding_revision": "old-model"}, 123), settings, catalog
        )
        is None
    )


def test_reuse_accepts_the_maintained_live_passage_count() -> None:
    settings = Settings(_env_file=None)
    catalog = Catalog.load(settings.data_dir)
    manifest = {**index_identity(settings, catalog), "passage_count": 123}
    snapshot = RedisSnapshot(
        manifest, 125, values={f"{settings.namespace}:expected-passages": b"125"}
    )
    assert current_manifest(snapshot, settings, catalog) == manifest


def test_reuse_validates_the_active_deployment_count() -> None:
    settings = Settings(_env_file=None)
    catalog = Catalog.load(settings.data_dir)
    manifest = {**index_identity(settings, catalog), "passage_count": 123}
    active = {"name": "camera_version_live", "count_key": "camera:version-count:live"}
    snapshot = RedisSnapshot(
        manifest,
        125,
        values={
            "camera:deploy": json.dumps({"active": active}).encode(),
            active["count_key"]: b"125",
        },
    )
    assert current_manifest(snapshot, settings, catalog) == manifest
    assert snapshot.searched_index == active["name"]


def test_reuse_observes_index_and_count_before_another_worker_commit() -> None:
    settings = Settings(_env_file=None)
    catalogue = service()[0].catalog
    manifest = {**index_identity(settings, catalogue), "passage_count": 123}
    count_key = f"{settings.namespace}:expected-passages"

    class UpdatingSnapshot(RedisSnapshot):
        locked = False

        @contextmanager
        def lock(self, *args, **kwargs):
            self.locked = True
            try:
                yield
            finally:
                self.locked = False

        def execute_command(self, *args):
            result = super().execute_command(*args)
            if not self.locked:
                # A worker commits immediately after FT.INFO but before GET count.
                self.values[count_key] = b"126"
            return result

    snapshot = UpdatingSnapshot(manifest, 125, values={count_key: b"125"})
    assert current_manifest(snapshot, settings, catalogue) == manifest


class SeedEncoder:
    def __init__(self) -> None:
        self.tokenizer = tokenizer()

    def embed(self, text: str) -> list[float]:
        return [1.0] + [0.0] * 383

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


@pytest.fixture
def seed_database(monkeypatch):
    if not os.getenv("TEST_REDIS_URL"):
        pytest.skip("Set TEST_REDIS_URL")
    settings = Settings(
        _env_file=None,
        redis_url=os.environ["TEST_REDIS_URL"],
        namespace="test_seed_" + uuid4().hex,
    )
    client = Redis.from_url(settings.redis_url)
    catalogue = service()[0].catalog
    encoder = SeedEncoder()
    monkeypatch.setattr(Catalog, "load", lambda _: catalogue)
    monkeypatch.setattr("seed.load.build_vectorizer", lambda _: encoder)
    monkeypatch.setattr("app.search.build_vectorizer", lambda _: encoder)
    monkeypatch.setattr("app.search.load_photos", lambda *_: {})
    try:
        yield settings, client, encoder
    finally:
        indexes = client.execute_command("FT._LIST")
        for name in indexes:
            if name.decode().startswith(settings.namespace):
                client.execute_command("FT.DROPINDEX", name, "DD")
        keys = list(client.scan_iter(match=settings.namespace + ":*"))
        if keys:
            client.delete(*keys)
        client.close()


def test_bootstrap_initializes_passage_accounting(seed_database):
    settings, client, _ = seed_database
    manifest = load(settings)
    assert (
        client.get(f"{settings.namespace}:expected-passages")
        == str(manifest["passage_count"]).encode()
    )


@pytest.mark.parametrize("indexed", [False, True])
@pytest.mark.parametrize("alternate", [False, True])
def test_if_needed_preserves_live_products_and_can_restart(seed_database, indexed, alternate):
    from app.search import build_searcher

    settings, client, encoder = seed_database
    manifest = load(settings)
    store = ProductStore(client, settings)
    index = SearchIndex.from_existing(settings.products_index, redis_client=client)
    worker = SyncWorker(store, encoder, index)
    added = product(product_id="demo-added")
    store.save(added)
    if indexed:
        worker.process_one()
    else:
        worker.pause(True)
    active = store.targets()[0]
    if alternate:
        active = {
            "name": settings.namespace + "_version_active",
            "prefix": settings.namespace + ":version:active",
            "count_key": settings.namespace + ":version-count:active",
        }
        schema = index.schema.to_dict()
        schema["index"].update(name=active["name"], prefix=active["prefix"])
        alternate_index = SearchIndex.from_dict(schema, redis_client=client)
        alternate_index.create()
        rows = [
            client.json().get(key) for key in client.scan_iter(match=settings.passage_prefix + ":*")
        ]
        alternate_index.load(rows, id_field="passage_id")
        client.set(active["count_key"], len(rows))
        # A retired bootstrap count must not determine the active version's readiness.
        client.set(store.count_key, 999)
    client.set(store.registry_key, json.dumps({"active": active, "stage": "idle"}))
    restarted = build_searcher(settings)
    assert restarted.index.name == active["name"]
    before = {key: client.dump(key) for key in client.scan_iter(match=settings.namespace + ":*")}
    reused = load(settings, if_needed=True)
    assert store.get(added.product_id) == added
    assert bool(store.passage_count(added.product_id)) is indexed
    assert reused == manifest
    assert before == {
        key: client.dump(key) for key in client.scan_iter(match=settings.namespace + ":*")
    }
    assert restarted.store.get(added.product_id) == added
    assert store.backlog()["unread"] == (0 if indexed else 1)
    restarted.index.disconnect()


@pytest.mark.parametrize("if_needed", [False, True])
def test_bootstrap_does_not_overwrite_an_existing_live_catalogue(seed_database, if_needed):
    settings, client, encoder = seed_database
    load(settings)
    store = ProductStore(client, settings)
    store.save(product(product_id="demo-added"))
    worker = SyncWorker(
        store, encoder, SearchIndex.from_existing(settings.products_index, redis_client=client)
    )
    worker.process_one()
    if if_needed:
        # A damaged live index requires an explicit live rebuild, never seed replacement.
        client.delete(store.passage_keys("demo-added")[0])
    before = {key: client.dump(key) for key in client.scan_iter(match=settings.namespace + ":*")}
    with pytest.raises(RuntimeError, match="live catalogue"):
        load(settings, if_needed=if_needed)
    assert before == {
        key: client.dump(key) for key in client.scan_iter(match=settings.namespace + ":*")
    }
