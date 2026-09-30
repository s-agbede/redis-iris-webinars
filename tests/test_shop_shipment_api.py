"""Delivery evidence crosses the real API, model loop, and MCP HTTP adapters."""

import json
from copy import deepcopy
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.shop.context_retriever import ContextRetrieverClient
from app.shop.service import ShopService
from tests.test_search import service
from tests.test_shop import Memory, Store
from tests.test_shop_tools import final_response, function_call, model_with

PURCHASES = [
    {
        "order_id": "SAM-DEMO-1001",
        "shopper_id": "alex",
        "product_id": "B09BBKVMCD",
        "shipment_id": "SHIP-1001",
        "purchased_at": "2026-04-18",
        "fictional": True,
    },
    {
        "order_id": "SAM-DEMO-1002",
        "shopper_id": "alex",
        "product_id": "MIC-DEMO-01",
        "shipment_id": "SHIP-1002",
        "purchased_at": "2026-09-22",
        "fictional": True,
    },
]
MICROPHONE = {
    "product_id": "MIC-DEMO-01",
    "product_title": "RØDE VideoMicro II",
    "product_description": "Fictional demo product record, without verified specifications.",
    "product_locale": "demo",
}
SHIPMENT = {
    "shipment_id": "SHIP-1002",
    "shopper_id": "alex",
    "order_id": "SAM-DEMO-1002",
    "status": "in_transit",
    "carrier": "Demo courier",
    "original_eta": "2026-09-29",
    "estimated_delivery": "2026-10-01",
    "latest_event": "Held at local depot",
    "updated_at": "2026-09-30T09:00:00Z",
    "fictional": True,
}
GENERATED = [
    {
        "name": "filter_purchase",
        "description": "Read purchases visible to the authorized shopper.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "minimum": 1}},
            "required": ["limit"],
            "additionalProperties": False,
        },
    },
    *[
        {
            "name": f"get_{entity}_by_id",
            "description": f"Read a linked {entity} by its ID.",
            "inputSchema": {
                "type": "object",
                "properties": {"id": {"type": "string"}},
                "required": ["id"],
                "additionalProperties": False,
            },
        }
        for entity in ("product", "shipment")
    ],
]


class DeliveryBackend:
    """HTTP protocol fixture with mutable current delivery evidence."""

    def __init__(self) -> None:
        self.shipment = deepcopy(SHIPMENT)
        self.requests: list[dict[str, Any]] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-Key"] == "shipment-test-alex"
        body = json.loads(request.content)
        self.requests.append(body)
        if body["method"] == "tools/list":
            result = {"tools": deepcopy(GENERATED)}
        else:
            assert body["method"] == "tools/call"
            params = body["params"]
            if params["name"] == "filter_purchase":
                assert params["arguments"] == {"limit": 10}
                payload = {"results": deepcopy(PURCHASES), "has_more": False}
            elif params["name"] == "get_product_by_id":
                assert params["arguments"] == {"id": "MIC-DEMO-01"}
                payload = deepcopy(MICROPHONE)
            else:
                assert params == {
                    "name": "get_shipment_by_id",
                    "arguments": {"id": "SHIP-1002"},
                }
                payload = deepcopy(self.shipment)
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


class DeliveryModel:
    """Script only the provider responses; keep the application's actual tool loop."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        definitions = {tool["name"]: tool for tool in body["tools"]}
        assert set(definitions) == {"search_catalogue", *(tool["name"] for tool in GENERATED)}
        for generated in GENERATED:
            actual = definitions[generated["name"]]
            assert actual["parameters"] == generated["inputSchema"]
            assert actual["description"] == generated["description"]
        outputs = [
            json.loads(item["output"])
            for item in body["input"]
            if item.get("type") == "function_call_output"
        ]
        if not outputs:
            output = function_call("filter_purchase", '{"limit":10}', "purchase-call")
        else:
            # Choose IDs from the returned purchase, never from the prompt or memory.
            purchase = max(outputs[0]["results"], key=lambda order: order["purchased_at"])
            if len(outputs) == 1:
                output = function_call(
                    "get_product_by_id", json.dumps({"id": purchase["product_id"]}), "product-call"
                )
            elif len(outputs) == 2:
                output = function_call(
                    "get_shipment_by_id",
                    json.dumps({"id": purchase["shipment_id"]}),
                    "shipment-call",
                )
            else:
                assert len(outputs) == 3
                product, shipment = outputs[1:]
                assert shipment["order_id"] == purchase["order_id"]
                if shipment["status"] == "delivered":
                    text = f"Your {product['product_title']} has been delivered in this demo."
                else:
                    text = (
                        f"Your {product['product_title']} is delayed in this demo. "
                        f"{shipment['latest_event']}; expected {shipment['estimated_delivery']}."
                    )
                output = final_response(text)
        return httpx.Response(200, json={"status": "completed", "output": [output]})


def delivery_shop(backend: DeliveryBackend, provider: DeliveryModel) -> ShopService:
    searcher, _, _ = service()
    retriever = ContextRetrieverClient(
        "https://retriever.example.test/mcp",
        {"alex": "shipment-test-alex", "jordan": "shipment-test-jordan"},
        client=httpx.Client(transport=httpx.MockTransport(backend.respond)),
    )
    return ShopService(
        searcher,
        Memory(),
        Store(),
        model_with(provider.respond),
        owner_prefix="shipment-api-test",
        context_retriever=retriever,
    )


def test_delivery_retrieval_and_same_session_refresh_preserve_exact_evidence() -> None:
    backend, provider = DeliveryBackend(), DeliveryModel()
    shop = delivery_shop(backend, provider)
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        session = client.post("/api/shop/sessions", json={"shopper_id": "alex"}).json()
        earlier_reply = ""
        for delivered in (False, True):
            if delivered:
                backend.shipment.update(
                    status="delivered",
                    estimated_delivery="2026-09-30",
                    latest_event="Delivered to recipient",
                    updated_at="2026-09-30T15:00:00Z",
                )
            response = client.post(
                "/api/shop/chat",
                json={
                    "shopper_id": "alex",
                    "session_id": session["session_id"],
                    "message": "Has it arrived now?" if delivered else "Where is my latest order?",
                    "mode": "session",
                },
            )
            assert response.status_code == 200, response.text
            turn = response.json()
            inspector = turn["inspector"]
            assert turn["products"] == []
            assert inspector["context"]["products"] == []
            assert [call["name"] for call in inspector["tool_calls"]] == [
                "filter_purchase",
                "get_product_by_id",
                "get_shipment_by_id",
            ]
            expected_outputs = [
                {"results": PURCHASES, "has_more": False},
                MICROPHONE,
                backend.shipment,
            ]
            assert [call["output"] for call in inspector["tool_calls"]] == expected_outputs
            assert inspector["answer_request"] == provider.requests[-1]
            assert [
                json.loads(item["output"])
                for item in inspector["answer_request"]["input"]
                if item.get("type") == "function_call_output"
            ] == expected_outputs
            assert "shipment-test" not in response.text
            assert "private-key" not in response.text
            if delivered:
                events = inspector["context"]["session"]["events"]
                assert [event["text"] for event in events if event["role"] == "ASSISTANT"] == [
                    earlier_reply
                ]
                model_context = json.loads(provider.requests[4]["input"][0]["content"])
                assert model_context["session"]["events"] == events
                assert "has been delivered" in turn["assistant"]
                assert "delayed" not in turn["assistant"]
            else:
                assert inspector["context"]["session"]["events"] == []
                assert "Held at local depot" in turn["assistant"]
                assert "2026-10-01" in turn["assistant"]
                earlier_reply = turn["assistant"]
        assert len(provider.requests) == 8
        assert [body["method"] for body in backend.requests] == [
            "tools/list",
            "tools/call",
            "tools/call",
            "tools/call",
        ] * 2
        assert len(shop.memory.session(session["session_id"]).events) == 4
        assert len(shop.session("alex", session["session_id"]).turns) == 2


@pytest.mark.parametrize("fault", ["missing-field", "invalid-date", "foreign"])
def test_untrusted_shipment_returns_retry_safe_503_without_saving_events(fault: str) -> None:
    backend, provider = DeliveryBackend(), DeliveryModel()
    if fault == "missing-field":
        del backend.shipment["latest_event"]
    elif fault == "invalid-date":
        backend.shipment["estimated_delivery"] = "2026-02-31"
    else:
        backend.shipment["shopper_id"] = "jordan"
    shop = delivery_shop(backend, provider)
    with TestClient(create_app(lambda: shop.searcher, shop_builder=lambda _: shop)) as client:
        session = client.post("/api/shop/sessions", json={"shopper_id": "alex"}).json()
        response = client.post(
            "/api/shop/chat",
            json={
                "shopper_id": "alex",
                "session_id": session["session_id"],
                "message": "Where is my latest order?",
                "mode": "session",
            },
        )
        assert response.status_code == 503
        assert response.json() == {
            "detail": "Context Retriever is unavailable. Please try again shortly.",
            "retry_safe": True,
        }
        assert len(provider.requests) == 3  # No model continuation with the untrusted shipment.
        assert backend.requests[-1]["params"]["name"] == "get_shipment_by_id"
        assert shop.memory.session(session["session_id"]).events == []
        assert shop.session("alex", session["session_id"]).turns == []
