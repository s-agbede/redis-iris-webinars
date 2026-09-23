"""Exercise the real SDK's requests and validation with an in-process HTTP transport."""

import importlib.util
import json
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

import httpx
import pytest
from redis_agent_memory import AgentMemory

STAMP = "2026-09-22T10:00:00Z"
NAMESPACE = {"namespaceId": "camera-shop", "name": "Camera shop", "path": "/camera-shop"}


def test_memory_adapter_is_available() -> None:
    assert importlib.util.find_spec("app.shop.memory") is not None


@pytest.fixture
def ram_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Any]]:
    from app.shop import memory as agent_memory

    clients: list[httpx.Client] = []

    def make(handler: Callable[[httpx.Request], httpx.Response], **kwargs: Any) -> Any:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        clients.append(client)
        monkeypatch.setattr(
            agent_memory,
            "AgentMemory",
            lambda *args, **options: AgentMemory(*args, client=client, **options),
        )
        return agent_memory.RAMClient(
            "https://memory.example.test",
            kwargs.get("store_id", "store-1"),
            "test-secret",
            namespace_id=kwargs.get("namespace_id", "camera-shop"),
        )

    yield make
    for client in clients:
        client.close()


def record(memory_id: str, text: str = "Owns a Sony camera", **changes: Any) -> dict[str, Any]:
    return {
        "id": memory_id,
        "text": text,
        "ownerId": "user-1",
        "memoryType": "semantic",
        "createdAt": STAMP,
        "updatedAt": STAMP,
        "namespaceRef": NAMESPACE,
        **changes,
    }


def event(role: str = "USER") -> dict[str, Any]:
    return {
        "eventId": "event-1",
        "sessionId": "session-1",
        "actorId": "user-1",
        "role": role,
        "content": [{"text": "I own a Sony camera"}],
        "createdAt": STAMP,
        "systemTimestamp": STAMP,
    }


def missing() -> httpx.Response:
    return httpx.Response(
        404,
        json={
            "title": "Not found",
            "type": "/errors/resource-not-found",
            "status": 404,
        },
    )


def test_append_event_uses_owner_utc_timestamp_and_namespace(ram_factory: Any) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(201, json={"event": event()})

    client = ram_factory(handler)
    assert client.append_event("session-1", "user-1", "USER", "I own a Sony camera") == "event-1"
    body = requests[0]
    assert body["sessionId"] == "session-1"
    assert body["actorId"] == "user-1"
    assert body["namespaceRef"] == {"namespaceId": "camera-shop"}
    assert body["content"] == [{"text": "I own a Sony camera"}]
    assert datetime.fromisoformat(body["createdAt"].replace("Z", "+00:00")).utcoffset() is not None


def test_search_scopes_owner_and_namespace_and_decodes_sdk_items(ram_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["filter"] == {
            "ownerId": {"eq": "user-1"},
            "namespaceRef": {"eq": "camera-shop"},
        }
        assert body["filterOp"] == "all"
        assert body["text"] == "What camera?"
        assert body["limit"] == 8
        return httpx.Response(200, json={"items": [record("memory-1")]})

    memories = ram_factory(handler).search("user-1", "What camera?")
    assert memories[0].id == "memory-1"
    assert memories[0].memory_type == "semantic"
    assert memories[0].updated_at == "2026-09-22T10:00:00+00:00"


def test_inventory_follows_opaque_tokens_without_vector_query(ram_factory: Any) -> None:
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        assert "text" not in body
        assert body["limit"] == 100
        assert body["filter"]["ownerId"] == {"eq": "user-1"}
        if len(requests) == 1:
            return httpx.Response(
                200, json={"items": [record("one")], "nextPageToken": "opaque/+="}
            )
        assert body["pageToken"] == "opaque/+="
        return httpx.Response(200, json={"items": [record("two")]})

    assert [item.id for item in ram_factory(handler).inventory("user-1")] == ["one", "two"]


def test_inventory_repeated_token_fails_explicitly(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    client = ram_factory(lambda _: httpx.Response(200, json={"items": [], "nextPageToken": "loop"}))
    with pytest.raises(MemoryError, match="complete inventory"):
        client.inventory("user-1")


def test_no_namespace_is_explicitly_unnamespaced(ram_factory: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["filter"] == {
            "ownerId": {"eq": "user-1"},
            "unnamespaced": True,
        }
        return httpx.Response(200, json={"items": []})

    assert ram_factory(handler, namespace_id=None).inventory("user-1") == []


def test_missing_session_is_empty(ram_factory: Any) -> None:
    session = ram_factory(lambda _: missing()).session("missing-session")
    assert session.events == []
    assert session.summary is None


def test_session_preserves_summary_and_retained_events(ram_factory: Any) -> None:
    client = ram_factory(
        lambda _: httpx.Response(
            200,
            json={
                "sessionId": "session-1",
                "ownerId": "user-1",
                "events": [event()],
                "namespaceRef": NAMESPACE,
                "summary": {
                    "text": "Earlier camera discussion",
                    "summarizedUpToEventId": "previous",
                    "createdAt": STAMP,
                    "updatedAt": STAMP,
                    "metadata": {},
                    "summarizedEvents": 4,
                },
            },
        )
    )
    session = client.session("session-1")
    assert session.summary == "Earlier camera discussion"
    assert session.events[0].text == "I own a Sony camera"
    assert session.events[0].role == "USER"


@pytest.mark.parametrize("status", [401, 403, 500])
def test_errors_never_disclose_response_bodies_or_credentials(
    ram_factory: Any, status: int
) -> None:
    from app.shop.memory import MemoryError

    client = ram_factory(lambda _: httpx.Response(status, text="test-secret private-service-body"))
    with pytest.raises(MemoryError) as error:
        client.session("session-1")
    assert "test-secret" not in str(error.value)
    assert "private-service-body" not in str(error.value)
    assert error.value.__suppress_context__


def test_search_rejects_cross_owner_response(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    client = ram_factory(
        lambda _: httpx.Response(
            200,
            json={
                "items": [record("wrong", ownerId="another-user")],
            },
        )
    )
    with pytest.raises(MemoryError, match="scope"):
        client.search("user-1", "camera")


def test_onboarding_is_idempotent_and_changed_facts_require_chat(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    stored: dict[str, dict[str, Any]] = {}
    writes: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            memory = stored.get(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json=memory) if memory else missing()
        body = json.loads(request.content)
        writes.append(body)
        for memory in body["memories"]:
            assert memory["ownerId"] == "user-1"
            assert memory["memoryType"] == "semantic"
            assert memory["namespaceRef"] == {"namespaceId": "camera-shop"}
            stored[memory["id"]] = record(memory["id"], memory["text"])
        return httpx.Response(201, json={"created": list(stored)})

    client = ram_factory(handler)
    first = client.create_facts("user-1", {"camera": "Owns a Sony camera", "interests": "Wildlife"})
    second = client.create_facts(
        "user-1", {"camera": "Owns a Sony camera", "interests": "Wildlife"}
    )
    assert first == second
    assert len(writes) == 1
    with pytest.raises(MemoryError, match="chat"):
        client.create_facts("user-1", {"camera": "Owns a Canon camera"})
    assert len(writes) == 1


def test_onboarding_reports_partial_success_without_raw_error(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    stored: dict[str, dict[str, Any]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            memory = stored.get(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json=memory) if memory else missing()
        memories = json.loads(request.content)["memories"]
        saved, failed = memories
        stored[saved["id"]] = record(saved["id"], saved["text"])
        return httpx.Response(
            201,
            json={
                "created": [saved["id"]],
                "errors": [{"id": failed["id"], "error": "private-service-body"}],
            },
        )

    with pytest.raises(MemoryError, match="1 of 2") as error:
        ram_factory(handler).create_facts("user-1", {"camera": "Sony", "interests": "Wildlife"})
    assert "private-service-body" not in str(error.value)


def test_onboarding_verifies_duplicate_create_by_reading_existing_record(ram_factory: Any) -> None:
    """A concurrent identical creation can return a per-ID error rather than a created ID."""
    stored: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=stored) if stored else missing()
        memory = json.loads(request.content)["memories"][0]
        stored.update(record(memory["id"], memory["text"]))
        return httpx.Response(
            201,
            json={
                "created": [],
                "errors": [
                    {"id": memory["id"], "error": "record already exists"},
                ],
            },
        )

    memories = ram_factory(handler).create_facts("user-1", {"camera": "Sony"})
    assert len(memories) == 1
    assert memories[0].text == "Sony"


def test_onboarding_validates_keys_before_writing(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    def handler(_: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid onboarding must not issue requests")

    with pytest.raises(MemoryError, match="camera, interests, preferences"):
        ram_factory(handler).create_facts("user-1", {"arbitrary": "value"})


def test_session_rejects_data_from_another_namespace(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    client = ram_factory(
        lambda _: httpx.Response(
            200,
            json={
                "sessionId": "session-1",
                "ownerId": "user-1",
                "events": [event()],
                "namespaceRef": {**NAMESPACE, "namespaceId": "another-application"},
            },
        )
    )
    with pytest.raises(MemoryError, match="namespace scope"):
        client.session("session-1")


def test_unnamespaced_recall_rejects_deprecated_namespace_labels(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    client = ram_factory(
        lambda _: httpx.Response(
            200,
            json={
                "items": [record("legacy", namespaceRef=None, namespace="other-application")],
            },
        ),
        namespace_id=None,
    )
    with pytest.raises(MemoryError, match="namespace scope"):
        client.inventory("user-1")


def test_malformed_success_response_becomes_safe_error(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    client = ram_factory(lambda _: httpx.Response(200, json={"items": [{"text": "private"}]}))
    with pytest.raises(MemoryError, match="invalid response") as error:
        client.inventory("user-1")
    assert "private" not in str(error.value)


def test_transport_error_does_not_retry_non_idempotent_event(ram_factory: Any) -> None:
    from app.shop.memory import MemoryError

    requests = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        raise httpx.ReadTimeout("private-service-body")

    with pytest.raises(MemoryError, match="could not be reached"):
        ram_factory(handler).append_event("session-1", "user-1", "USER", "Camera fact")
    assert requests == 1


def test_fact_ids_are_stable_and_scoped_to_store_namespace_owner(ram_factory: Any) -> None:
    ids: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            ids.append(request.url.path.rsplit("/", 1)[-1])
            return missing()
        return httpx.Response(500, text="write intentionally blocked")

    from app.shop.memory import MemoryError

    for store, namespace, owner in [
        ("store-1", "camera-shop", "user-1"),
        ("store-1", "camera-shop", "user-1"),
        ("store-2", "camera-shop", "user-1"),
        ("store-1", "other-namespace", "user-1"),
        ("store-1", "camera-shop", "user-2"),
    ]:
        with pytest.raises(MemoryError):
            ram_factory(handler, store_id=store, namespace_id=namespace).create_facts(
                owner, {"camera": "Sony"}
            )
    assert ids[0] == ids[1]
    assert len(set(ids)) == 4
    assert all(len(memory_id) <= 64 for memory_id in ids)
