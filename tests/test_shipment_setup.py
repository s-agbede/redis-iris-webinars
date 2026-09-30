"""Atomic demo migration and controlled shipment replay, using real Redis JSON."""

import json
import os
from uuid import uuid4

import httpx
import pytest
from redis import Redis

pytest.importorskip("context_surfaces", reason="Install the context-retriever extra")


@pytest.fixture
def redis_keys():
    url = os.getenv("TEST_REDIS_URL")
    if not url:
        pytest.skip("Set TEST_REDIS_URL for isolated JSON integration tests")
    client = Redis.from_url(url, socket_timeout=5)
    prefix = f"test_shipment_{uuid4().hex}:"
    keys = [prefix + str(i) for i in range(4)]
    try:
        yield client, keys
    finally:
        client.delete(*keys)
        client.close()


def test_migration_upgrades_only_known_values_and_is_repeatable(redis_keys) -> None:
    from scripts.setup_shipment_demo import migrate_documents

    client, (old, new, untouched, _) = redis_keys
    previous = {old: {"version": 1}}
    desired = {old: {"version": 2}, new: {"version": 2}}
    client.json().set(old, "$", previous[old])
    client.json().set(untouched, "$", {"unrelated": True})
    assert migrate_documents(client, previous, desired) == 2
    assert migrate_documents(client, previous, desired) == 0
    assert client.json().get(old) == desired[old]
    assert client.json().get(new) == desired[new]
    assert client.json().get(untouched) == {"unrelated": True}


@pytest.mark.parametrize("value", [{"custom": True}, None])
def test_conflict_aborts_all_writes(redis_keys, value) -> None:
    from scripts.check_context_retriever import SmokeError
    from scripts.setup_shipment_demo import migrate_documents

    client, (old, new, _, _) = redis_keys
    client.json().set(old, "$", value)
    with pytest.raises(SmokeError, match="different"):
        migrate_documents(client, {old: {"version": 1}}, {old: {"version": 2}, new: {}})
    assert client.json().get(old) == value
    assert not client.exists(new)


def test_replay_changes_only_shipment_and_can_restore_fixture(redis_keys) -> None:
    from scripts.setup_shipment_demo import migrate_documents, shipment_states

    client, (key, untouched, _, _) = redis_keys
    delayed, delivered = shipment_states()
    client.json().set(key, "$", delayed)
    client.json().set(untouched, "$", {"keep": "me"})
    assert migrate_documents(client, {key: delayed}, {key: delivered}) == 1
    assert client.json().get(key)["status"] == "delivered"
    assert migrate_documents(client, {key: delivered}, {key: delayed}) == 1
    assert client.json().get(key) == delayed
    assert client.json().get(untouched) == {"keep": "me"}


def test_migration_rejects_changed_json_boolean_type(redis_keys) -> None:
    from scripts.check_context_retriever import SmokeError
    from scripts.setup_shipment_demo import migrate_documents

    client, (key, _, _, _) = redis_keys
    client.json().set(key, "$", {"fictional": 1})
    with pytest.raises(SmokeError, match="different"):
        migrate_documents(client, {key: {"fictional": True}}, {key: {"fictional": True, "v": 2}})
    assert client.json().get(key) == {"fictional": 1}


def test_shipment_replay_preserves_identity_and_uses_explicit_dates() -> None:
    from app.shop.context_retriever import ShipmentRecord
    from scripts.setup_shipment_demo import shipment_states

    delayed, delivered = shipment_states()
    assert delayed["status"] == "in_transit"
    assert delivered["status"] == "delivered"
    assert delayed["estimated_delivery"] == "2026-10-01"
    assert {key for key in delayed if delayed[key] != delivered[key]} == {
        "status",
        "latest_event",
        "updated_at",
    }
    ShipmentRecord.model_validate(delayed)
    ShipmentRecord.model_validate(delivered)


@pytest.mark.asyncio
@pytest.mark.parametrize("foreign_prefix", [False, True])
async def test_publish_preserves_other_settings_and_refuses_foreign_prefix(
    tmp_path, foreign_prefix
):
    from scripts.check_context_retriever import SmokeError
    from scripts.setup_shipment_demo import SetupSettings, publish
    from seed.shop_context import data_model

    remote_model = data_model()
    if foreign_prefix:
        remote_model["entities"][0]["redis_key_template"] = "production:shopper:{shopper_id}"
    writes = []

    def respond(request):
        if request.method == "PUT":
            writes.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "demo",
                "name": "camera-shop-context-smoke",
                "owner": "test",
                "status": "active",
                "data_model": remote_model,
                "tools": [],
                "created_at": "2026-09-29T09:00:00Z",
                "updated_at": "2026-09-30T09:00:00Z",
            },
        )

    settings = SetupSettings(_env_file=None, ctx_admin_key="test-secret", ctx_surface_id="demo")
    backup = tmp_path / "model.json"
    if foreign_prefix:
        with pytest.raises(SmokeError, match="prefix"):
            await publish(settings, backup, transport=httpx.MockTransport(respond))
        assert writes == []
        assert not backup.exists()
    else:
        await publish(settings, backup, transport=httpx.MockTransport(respond))
        assert writes == [{"data_model": data_model()}]
        assert json.loads(backup.read_text()) == remote_model
        assert "test-secret" not in backup.read_text()
