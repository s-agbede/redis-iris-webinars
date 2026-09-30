"""Discover generated schemas and let the agent choose each MCP call."""

import json
from copy import deepcopy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.shop.context_retriever import ContextRetrieverClient, ContextRetrieverError
from app.shop.models import Onboarding
from app.shop.service import ShopService
from tests.test_search import service
from tests.test_shop import Memory, Store
from tests.test_shop_tools import final_response, function_call, model_with

GENERATED = [
    {
        "name": "filter_purchase",
        "description": "Generated purchase lookup for the authorized shopper.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1}},
            "additionalProperties": False,
        },
    },
    {
        "name": "follow_purchase_product",
        "description": "Generated relationship from a purchase to its product.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
            "additionalProperties": False,
        },
    },
]


class MCPBackend:
    def __init__(self, fault: str = "") -> None:
        self.fault = fault
        self.requests: list[tuple[str, dict]] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        shopper = request.headers["X-API-Key"].removeprefix("test-key-")
        self.requests.append((shopper, body))
        if self.fault == "timeout":
            raise httpx.ReadTimeout("test-key-alex", request=request)
        if self.fault == "expired":
            return httpx.Response(401, text="test-key-alex")
        if self.fault == "invalid-json":
            return httpx.Response(200, text="not JSON")
        if body["method"] == "tools/list":
            result = {"tools": deepcopy(GENERATED)}
            if self.fault == "duplicate":
                result["tools"].append(result["tools"][0])
            if self.fault == "schema":
                result["tools"][0]["inputSchema"] = {"type": "made-up"}
        else:
            assert body["method"] == "tools/call"
            name = body["params"]["name"]
            if name == "filter_purchase":
                payload = {
                    "results": [
                        {
                            "order_id": f"order-{shopper}",
                            "shopper_id": shopper,
                            "product_id": f"product-{shopper}",
                            "purchased_at": "2026-09-01",
                            "fictional": True,
                        }
                    ],
                    "has_more": False,
                }
                if self.fault == "empty":
                    payload["results"] = []
                if self.fault == "foreign":
                    payload["results"][0]["shopper_id"] = "jordan" if shopper == "alex" else "alex"
                if self.fault == "invalid-date":
                    payload["results"][0]["purchased_at"] = "2026-02-31"
                if self.fault == "not-fictional":
                    payload["results"][0]["fictional"] = False
                if self.fault == "missing-order-field":
                    del payload["results"][0]["product_id"]
                if self.fault == "truncated":
                    payload["has_more"] = True

            else:
                assert name == "follow_purchase_product"
                payload = {
                    "product_id": f"product-{shopper}",
                    "product_title": f"Retrieved {shopper} camera",
                    "product_description": "Source camera description",
                }
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
            if self.fault == "structured":
                result = {"structuredContent": payload}
            if self.fault == "invalid-tag-field":
                result = {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Error executing tool: tag_conditions[0] names a field Shopper "
                                "does not have as a tag field: it has none test-key-alex"
                            ),
                        }
                    ],
                }
            if self.fault in {"missing-id", "denied-id"}:
                reason = "access denied: " if self.fault == "denied-id" else ""
                result = {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Error executing tool: get by ID failed: "
                                + reason
                                + "document not found: private-record-test-key-alex"
                            ),
                        }
                    ],
                }
            if self.fault == "tool-error":
                result = {"isError": True, "content": [{"type": "text", "text": "test-key-alex"}]}
        envelope = {"jsonrpc": "2.0", "id": body["id"], "result": result}
        if self.fault == "rpc":
            envelope = {"jsonrpc": "2.0", "id": body["id"], "error": {"message": "test-key-alex"}}
        if self.fault == "wrong-id":
            envelope["id"] = "wrong"
        return httpx.Response(200, json=envelope)


def client_for(backend: MCPBackend) -> ContextRetrieverClient:
    return ContextRetrieverClient(
        "https://retriever.example.test/mcp",
        {"alex": "test-key-alex", "jordan": "test-key-jordan"},
        client=httpx.Client(transport=httpx.MockTransport(backend.respond)),
    )


def test_discovery_preserves_generated_names_descriptions_and_schemas_per_shopper() -> None:
    backend = MCPBackend()
    client = client_for(backend)
    for shopper in ("alex", "jordan"):
        tools = client.list_tools(shopper)
        for actual, expected in zip(tools, GENERATED, strict=True):
            assert actual.name == expected["name"]
            assert actual.description == expected["description"]
            assert actual.parameters == expected["inputSchema"]
            assert actual.strict is False
    assert [who for who, _ in backend.requests] == ["alex", "jordan"]
    assert all(body["method"] == "tools/list" for _, body in backend.requests)


@pytest.mark.parametrize("fault", ["", "structured", "empty"])
def test_one_selected_tool_call_does_not_eagerly_fetch_products(fault: str) -> None:
    backend = MCPBackend(fault)
    client = client_for(backend)
    tool = client.list_tools("jordan")[0]
    result = client.call_tool("jordan", tool, {"limit": 2})
    assert (
        result["results"] == []
        if fault == "empty"
        else result["results"][0]["shopper_id"] == "jordan"
    )
    assert [body["method"] for _, body in backend.requests] == ["tools/list", "tools/call"]
    assert backend.requests[-1][1]["params"] == {
        "name": "filter_purchase",
        "arguments": {"limit": 2},
    }


def test_discovered_schema_rejects_bad_arguments_before_network_execution() -> None:
    backend = MCPBackend()
    client = client_for(backend)
    tool = client.list_tools("alex")[0]
    with pytest.raises(ContextRetrieverError):
        client.call_tool("alex", tool, {"limit": "2"})
    assert len(backend.requests) == 1


@pytest.mark.parametrize("fault", ["timeout", "expired", "duplicate", "schema", "rpc", "wrong-id"])
def test_discovery_failure_is_safe_and_never_exposes_secrets(fault: str) -> None:
    with pytest.raises(ContextRetrieverError) as error:
        client_for(MCPBackend(fault)).list_tools("alex")
    assert "test-key" not in str(error.value)


@pytest.mark.parametrize(
    "fault",
    [
        "foreign",
        "invalid-date",
        "not-fictional",
        "missing-order-field",
        "tool-error",
        "invalid-json",
        "rpc",
        "wrong-id",
    ],
)
def test_failed_or_untrusted_tool_result_is_not_passed_to_the_model(fault: str) -> None:
    backend = MCPBackend()
    client = client_for(backend)
    tool = client.list_tools("alex")[0]
    backend.fault = fault
    with pytest.raises(ContextRetrieverError) as error:
        client.call_tool("alex", tool, {})
    assert "test-key" not in str(error.value)


def test_partial_results_retain_pagination_metadata_for_the_agent() -> None:
    backend = MCPBackend("truncated")
    client = client_for(backend)
    tool = client.list_tools("alex")[0]
    assert client.call_tool("alex", tool, {})["has_more"] is True
    assert len(backend.requests) == 2


def test_discovery_follows_cursors_without_repeating_or_dropping_tools() -> None:
    cursors = []

    def respond(request):
        body = json.loads(request.content)
        cursor = body["params"].get("cursor")
        cursors.append(cursor)
        result = (
            {"tools": [GENERATED[1]]}
            if cursor
            else {"tools": [GENERATED[0]], "nextCursor": "next-page"}
        )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    client = ContextRetrieverClient(
        "https://retriever.example.test/mcp",
        {"alex": "test-key-alex", "jordan": "test-key-jordan"},
        client=httpx.Client(transport=httpx.MockTransport(respond)),
    )
    assert [t.name for t in client.list_tools("alex")] == [t["name"] for t in GENERATED]
    assert cursors == [None, "next-page"]


def test_unknown_shopper_is_rejected_before_network_access() -> None:
    backend = MCPBackend()
    with pytest.raises(ContextRetrieverError):
        client_for(backend).list_tools("unknown")
    assert backend.requests == []


def test_unresolvable_discovered_schema_fails_safely_without_calling_mcp() -> None:
    backend = MCPBackend()
    client = client_for(backend)
    tool = client.list_tools("alex")[1]
    tool.parameters["properties"] = {"id": {"$ref": "#/$defs/missing"}}
    with pytest.raises(ContextRetrieverError):
        client.call_tool("alex", tool, {"id": "order-alex"})
    assert len(backend.requests) == 1


@pytest.mark.parametrize("shopper", ["alex", "jordan"])
@pytest.mark.parametrize("mode", ["none", "session", "both"])
def test_model_chooses_generated_relationship_and_http_capture_preserves_it(
    shopper: str, mode: str
) -> None:
    backend = MCPBackend()
    requests: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        definitions = {item["name"]: item for item in body["tools"]}
        assert set(definitions) == {"search_catalogue", *(t["name"] for t in GENERATED)}
        assert "get_purchase_history" not in definitions
        for generated in GENERATED:
            tool = definitions[generated["name"]]
            assert tool["parameters"] == generated["inputSchema"]
            assert tool["description"] == generated["description"]
        if len(requests) == 1:
            assert len(backend.requests) == 1  # Discovery only; the agent hasn't called anything.
            output = function_call("filter_purchase", '{"limit":2}')
        elif len(requests) == 2:
            order = json.loads(body["input"][-1]["output"])["results"][0]
            assert order["shopper_id"] == shopper
            output = function_call(
                "follow_purchase_product", json.dumps({"id": order["order_id"]}), "call-2"
            )
        else:
            product = json.loads(body["input"][-1]["output"])
            output = final_response("Your fictional order contains this camera.")
            output["content"][0]["text"] = json.dumps(
                {
                    "text": "Your fictional order contains this camera.",
                    "product_ids": [product["product_id"]],
                }
            )
        return httpx.Response(200, json={"status": "completed", "output": [output]})

    searcher, _, _ = service()
    retriever = client_for(backend)
    shop = ShopService(
        searcher,
        Memory(),
        Store(),
        model_with(respond),
        owner_prefix="mcp-test",
        context_retriever=retriever,
    )
    with TestClient(create_app(lambda: searcher, shop_builder=lambda _: shop)) as client:
        session = client.post("/api/shop/sessions", json={"shopper_id": shopper}).json()
        shop.onboard(shopper, Onboarding(preferences="Lightweight gear"))
        shop.memory.append_event(session["session_id"], session["owner_id"], "USER", "Earlier turn")
        response = client.post(
            "/api/shop/chat",
            json={
                "shopper_id": shopper,
                "session_id": session["session_id"],
                "message": "What did I buy?",
                "mode": mode,
            },
        )
        assert response.status_code == 200, response.text
        turn = response.json()
        assert [call["name"] for call in turn["inspector"]["tool_calls"]] == [
            "filter_purchase",
            "follow_purchase_product",
        ]
        assert turn["products"][0]["title"] == f"Retrieved {shopper} camera"
        context = turn["inspector"]["context"]
        assert context["shopper_id"] == shopper
        assert bool(context["session"]["events"]) == (mode != "none")
        assert bool(context["memories"]) == (mode == "both")
        assert {who for who, _ in backend.requests} == {shopper}
        assert "test-key" not in response.text
        assert turn["inspector"]["answer_request"] == requests[-1]
    assert retriever._client.is_closed


@pytest.mark.parametrize(
    "fault,code,hint",
    [
        ("invalid-tag-field", "invalid_filter_field", "indexed"),
        ("missing-id", "record_unavailable", "not exist"),
        ("denied-id", "record_unavailable", "not exist"),
    ],
)
def test_known_query_error_reaches_model_without_service_text(fault, code, hint) -> None:
    backend = MCPBackend(fault)
    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            output = function_call("filter_purchase", '{"limit":1}')
        elif len(requests) == 2:
            error = json.loads(body["input"][-1]["output"])
            assert error["isError"] is True
            assert error["error"] == code
            assert hint in error["message"]
            assert "test-key" not in json.dumps(error)
            assert "private-record" not in json.dumps(error)
            backend.fault = ""
            output = function_call("filter_purchase", '{"limit":2}', "corrected-call")
        else:
            assert json.loads(body["input"][-1]["output"])["results"][0]["shopper_id"] == "alex"
            output = final_response(
                "Your fictional order was retrieved after correcting the query."
            )
        return httpx.Response(200, json={"status": "completed", "output": [output]})

    searcher, _, _ = service()
    shop = ShopService(
        searcher,
        Memory(),
        Store(),
        model_with(respond),
        owner_prefix="corrected-query-test",
        context_retriever=client_for(backend),
    )
    session = shop.new_session("alex")
    turn = shop.turn("alex", session.session_id, "What did I buy?", "none")
    assert len(turn.inspector.tool_calls) == 2
    assert turn.inspector.tool_calls[0].output["isError"] is True
    assert turn.inspector.tool_calls[1].output["results"][0]["shopper_id"] == "alex"
    assert len(shop.memory.session(session.session_id).events) == 2
