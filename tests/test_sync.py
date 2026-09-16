"""Real Redis lifecycle tests; each test owns a unique namespace."""

import os
from uuid import uuid4

import pytest
import yaml
from redis import Redis
from redisvl.index import SearchIndex

from app.embeddings import build_vectorizer
from app.models import CameraProduct
from app.product_store import ProductStore
from app.settings import ROOT, Settings
from app.sync import SyncWorker
from seed.load import configure_schema

pytestmark = pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="Set TEST_REDIS_URL")


@pytest.fixture(scope="module")
def encoder():
    return build_vectorizer(Settings())


@pytest.fixture
def lab(encoder):
    settings = Settings(
        redis_url=os.environ["TEST_REDIS_URL"], namespace="test_sync_" + uuid4().hex
    )
    client = Redis.from_url(settings.redis_url)
    schema = yaml.safe_load((ROOT / "schemas/passages.yaml").read_text())
    configure_schema(schema, settings)
    index = SearchIndex.from_dict(schema, redis_client=client)
    index.create()
    store = ProductStore(client, settings)
    worker = SyncWorker(store, encoder, index)
    yield store, worker, index
    index.delete(drop=True)
    keys = list(client.scan_iter(match=settings.namespace + ":*"))
    if keys:
        client.delete(*keys)
    client.close()


def product() -> CameraProduct:
    return CameraProduct(
        product_id="demo-camera",
        product_title="Aurora ZV Demo Camera",
        product_brand="Demo",
        product_color="White",
        product_description="Fictional demonstration camera for video recording.",
    )


def test_paused_add_resumes_without_resubmission(lab):
    store, worker, index = lab
    worker.pause(True)
    store.save(product())
    assert store.get("demo-camera") == product()
    assert store.backlog()["unread"] == 1
    assert worker.process_one() is False
    assert int(index.info()["num_docs"]) == 0
    worker.pause(False)
    assert worker.process_one() is True
    assert store.passage_count("demo-camera") > 0
    assert store.backlog() == {"unread": 0, "pending": 0}


def test_delete_and_replayed_event_cannot_resurrect_product(lab):
    store, worker, index = lab
    store.save(product())
    worker.process_one()
    store.delete("demo-camera")
    assert store.get("demo-camera") is None
    assert store.passage_count("demo-camera") > 0
    worker.process_one()
    store.client.xadd(store.events_key, {"product_id": "demo-camera"})
    worker.process_one()
    assert store.passage_count("demo-camera") == 0
    assert int(index.info()["num_docs"]) == 0


def test_worker_recovers_delivered_unacknowledged_event(lab):
    store, worker, _ = lab
    store.save(product())
    store.client.xreadgroup(store.group, "dead-worker", {store.events_key: ">"}, count=1)
    assert store.backlog()["pending"] == 1
    assert worker.process_one(reclaim_idle_ms=0)
    assert store.passage_count("demo-camera") > 0
    assert store.backlog() == {"unread": 0, "pending": 0}


def test_change_during_embedding_does_not_publish_stale_passages(lab):
    store, worker, _ = lab
    store.save(product())
    original = worker.encoder

    class DeletingEncoder:
        tokenizer = original.tokenizer

        def embed_many(self, texts):
            store.delete("demo-camera")
            return original.embed_many(texts)

    worker.encoder = DeletingEncoder()
    worker.process_one()
    assert store.passage_count("demo-camera") == 0
    worker.encoder = original
    worker.process_one()
    assert store.get("demo-camera") is None


def test_reset_only_deletes_demo_products(lab):
    store, worker, _ = lab
    original = product().model_copy(update={"product_id": "original"})
    store.save(original, demo=False)
    store.save(product())
    while worker.process_one():
        pass
    store.reset()
    while worker.process_one():
        pass
    assert store.get("original") == original
    assert store.get("demo-camera") is None
    assert store.passage_count("demo-camera") == 0


def test_real_search_visibility_and_stale_indexed_view(lab):
    from app.catalog import Catalog, DataManifest
    from app.models import CompareRequest
    from app.search import Searcher

    store, worker, index = lab
    catalogue = Catalog(
        {},
        [],
        DataManifest(
            source="test",
            source_revision="test",
            product_count=0,
            query_count=0,
            judgement_count=0,
            checksums={},
        ),
        "test",
    )
    searcher = Searcher(index, worker.encoder, catalogue, store.settings, store=store)
    query = CompareRequest(query="Aurora ZV Demo Camera")
    worker.pause(True)
    store.save(product())
    assert all(not r.hits for r in searcher.compare(query).results)
    worker.pause(False)
    worker.process_one()
    for result in searcher.compare(query).results:
        assert result.error is None
        assert result.hits[0].product_id == "demo-camera"
    worker.pause(True)
    store.delete("demo-camera")
    assert all(not r.hits for r in searcher.compare(query).results)
    stale = searcher.compare(query.model_copy(update={"indexed_view": True}))
    assert all(r.hits[0].available is False for r in stale.results)
    assert stale.results[0].hits[0].title == product().product_title
    worker.pause(False)
    worker.process_one()
    assert all(not r.hits for r in searcher.compare(query).results)


def test_reset_clears_presenter_history_and_retries_keep_unique_keys(lab):
    store, worker, _ = lab
    store.save(product())
    worker.process_one()
    keys = store.passage_keys("demo-camera")
    store.client.xadd(store.events_key, {"product_id": "demo-camera"})
    worker.process_one()
    assert sorted(store.passage_keys("demo-camera")) == sorted(keys)
    store.reset()
    while worker.process_one():
        pass
    assert store.demo_ids() == []


def test_autocomplete_waits_for_indexing_and_keeps_existing_suggestions(lab):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.test_search import service

    store, worker, index = lab
    searcher, _, _ = service()
    searcher.store = store
    searcher.index = index
    searcher.settings = store.settings
    app = create_app()
    app.state.searcher = searcher
    # Do not start a background worker: advance synchronization explicitly.
    client = TestClient(app)
    worker.pause(True)
    store.save(product())
    url = "/api/suggestions?prefix=Aurora"
    assert client.get(url).json() == []
    worker.pause(False)
    worker.process_one()
    assert client.get(url).json() == [product().product_title]
    worker.pause(True)
    assert client.get(url).json() == [product().product_title]
    store.delete(product().product_id)
    assert client.get(url).json() == []


def test_product_failure_moves_to_dead_letters_and_can_be_retried(lab):
    store, worker, _ = lab
    original = worker.encoder

    class BrokenEncoder:
        tokenizer = original.tokenizer

        def embed_many(self, texts):
            raise ValueError("Cannot prepare this product")

    worker.encoder = BrokenEncoder()
    worker.retry_base_seconds = 0
    store.save(product())
    for _ in range(3):
        assert worker.process_one(reclaim_idle_ms=0)
    assert store.backlog() == {"unread": 0, "pending": 0}
    failures = worker.failures.list()
    assert len(failures) == 1
    failure = failures[0]
    assert failure.product_id == product().product_id
    assert failure.attempts == 3
    assert "Cannot prepare" in failure.error
    worker.encoder = original
    worker.failures.retry(failure.event_id)
    assert worker.failures.list() == []
    assert store.backlog()["unread"] == 1
    worker.process_one()
    assert store.passage_count(product().product_id) > 0


def test_connection_failure_does_not_consume_product_retry_budget(lab):
    from redis.exceptions import ConnectionError

    store, worker, _ = lab
    original = worker.encoder

    class DisconnectedEncoder:
        tokenizer = original.tokenizer

        def embed_many(self, texts):
            raise ConnectionError("Redis connection unavailable")

    worker.encoder = DisconnectedEncoder()
    store.save(product())
    with pytest.raises(ConnectionError):
        worker.process_one()
    assert worker.failures.list() == []
    assert store.client.hlen(worker.failures.attempts_key) == 0
    assert store.backlog()["pending"] == 1


def test_product_backoff_does_not_block_new_events(lab):
    store, worker, _ = lab
    original = worker.encoder

    class BrokenEncoder:
        tokenizer = original.tokenizer

        def embed_many(self, texts):
            raise ValueError("bad product")

    worker.encoder = BrokenEncoder()
    store.save(product())
    worker.process_one()
    worker.encoder = original
    second = product().model_copy(update={"product_id": "second"})
    store.save(second)
    worker.process_one(reclaim_idle_ms=0)
    assert store.passage_count("second") > 0
    assert store.passage_count(product().product_id) == 0


def test_failed_event_retry_is_visible_through_presenter_api(lab):
    from fastapi.testclient import TestClient

    from app.main import create_app

    store, worker, _ = lab
    store.save(product())
    rows = store.client.xreadgroup(store.group, "test", {store.events_key: ">"}, count=1)
    event_id = rows[0][1][0][0]
    worker.failures.record(
        event_id, product().product_id, ValueError("bad input"), max_attempts=1, base_seconds=0
    )
    app = create_app()
    app.state.sync_worker = worker
    client = TestClient(app)
    response = client.get("/api/lab")
    assert response.status_code == 200
    body = response.json()
    assert body["failed_count"] == 1
    failure_id = body["failures"][0]["event_id"]
    response = client.post(f"/api/lab/failures/{failure_id}/retry")
    assert response.status_code == 200
    assert response.json()["failed_count"] == 0
    assert response.json()["unread"] == 1
    assert client.post(f"/api/lab/failures/{failure_id}/retry").status_code == 409
    client.close()
