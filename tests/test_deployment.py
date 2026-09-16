"""Isolated real Redis deployment lifecycle checks."""

import os

import pytest

from app.deployment import DeploymentManager
from tests.test_sync import encoder, lab, product  # noqa: F401

pytestmark = [pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="Set TEST_REDIS_URL")]


def build(manager):
    manager.start_build()
    manager.thread.join(timeout=30)
    assert manager.status()["stage"] == "ready", manager.status()


def test_validated_revision_guards_switch_and_rollback(lab):  # noqa: F811
    store, worker, index = lab
    store.save(product())
    worker.process_one()
    manager = DeploymentManager(store, worker.encoder, index)
    try:
        build(manager)
        manager.validate()
        assert manager.status()["stage"] == "validated"
        store.save(product().model_copy(update={"product_color": "Black"}))
        with pytest.raises(ValueError):
            manager.switch()
        worker.process_one()
        with pytest.raises(ValueError):
            manager.switch()
        manager.validate()
        manager.switch()
        assert manager.status()["previous_index"] == store.settings.products_index
        manager.rollback()
        assert manager.status()["active_index"] == store.settings.products_index
    finally:
        manager.reset()
        manager.close()


def test_build_observes_live_deletion_and_reset_preserves_original(lab):  # noqa: F811
    store, worker, index = lab
    store.save(product())
    worker.process_one()
    manager = DeploymentManager(store, worker.encoder, index)
    try:
        build(manager)
        store.delete(product().product_id)
        worker.process_one()
        manager.validate()
        assert all(check["passed"] for check in manager.status()["validation"])
        manager.reset()
        assert index.exists()
        assert manager.status()["candidate_index"] is None
    finally:
        manager.close()


def test_validation_runs_reviewed_unfiltered_text_and_hybrid_cases(lab):  # noqa: F811
    store, worker, index = lab
    store.save(
        product().model_copy(
            update={
                "product_id": "B09BBKVMCD",
                "product_title": "Sony ZV-E10 vlog camera",
                "product_brand": "Sony",
            }
        )
    )
    worker.process_one()
    manager = DeploymentManager(store, worker.encoder, index)
    try:
        build(manager)
        manager.validate()
        checks = manager.status()["validation"]
        reviewed = [check for check in checks if check["name"].startswith("Reviewed ")]
        assert len(reviewed) == 6
        assert all(check["passed"] for check in reviewed), reviewed
    finally:
        manager.reset()
        manager.close()


def test_failed_coverage_blocks_switch(lab):  # noqa: F811
    store, worker, index = lab
    store.save(product())
    worker.process_one()
    manager = DeploymentManager(store, worker.encoder, index)
    try:
        build(manager)
        candidate = store.targets()[1]
        store.client.delete(store.passage_keys(product().product_id, candidate["prefix"])[0])
        assert manager.validate()["stage"] == "ready"
        with pytest.raises(ValueError):
            manager.switch()
        assert manager.status()["active_index"] == index.name
    finally:
        manager.reset()
        manager.close()


def test_missing_retained_passage_blocks_rollback(lab):  # noqa: F811
    store, worker, index = lab
    store.save(product())
    worker.process_one()
    manager = DeploymentManager(store, worker.encoder, index)
    try:
        build(manager)
        manager.validate()
        manager.switch()
        key = store.passage_keys(product().product_id, store.settings.passage_prefix)[0]
        saved = store.client.json().get(key)
        store.client.delete(key)
        with pytest.raises(ValueError, match="incomplete"):
            manager.rollback()
    finally:
        # Undo only the intentional corruption, preserving the expected-count checkpoint.
        store.client.json().set(key, "$", saved)
        manager.rollback()
        manager.reset()
        manager.close()


def test_cleanup_during_inflight_comparison_retries_current_index(lab):  # noqa: F811
    from app.catalog import Catalog
    from app.models import CompareRequest
    from app.search import Searcher

    store, worker, index = lab
    store.save(product())
    worker.process_one()
    manager = DeploymentManager(store, worker.encoder, index)

    class CleanupDuringEmbedding:
        cleaned_up = False

        def embed(self, query):
            if not self.cleaned_up:
                self.cleaned_up = True
                manager.rollback()
                manager.reset()
            return worker.encoder.embed(query)

    try:
        build(manager)
        manager.validate()
        manager.switch()
        searcher = Searcher(
            index,
            CleanupDuringEmbedding(),
            Catalog.load(store.settings.data_dir),
            store.settings,
            store=store,
        )
        result = searcher.compare(CompareRequest(query="Aurora ZV Demo Camera"))
        assert all(mode.error is None for mode in result.results), result
        assert all(mode.hits[0].product_id == "demo-camera" for mode in result.results)
        assert manager.status()["active_index"] == index.name
    finally:
        manager.reset()
        manager.close()
