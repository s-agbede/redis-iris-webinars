"""Shipment records are validated before they become model evidence."""

import json

import httpx
import pytest

from app.shop.context_retriever import ContextRetrieverClient, ContextRetrieverError
from app.shop.models import ToolDefinition


def shipment() -> dict:
    return {
        "shipment_id": "SHIP-1002",
        "order_id": "SAM-DEMO-1002",
        "shopper_id": "alex",
        "status": "in_transit",
        "carrier": "Demo courier",
        "original_eta": "2026-09-29",
        "estimated_delivery": "2026-10-01",
        "latest_event": "Held at local depot",
        "updated_at": "2026-09-30T09:00:00Z",
        "fictional": True,
    }


def retrieve(record: dict, *, nested: bool = False):
    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        payload = {"results": [record]} if nested else record
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"structuredContent": payload},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        client = ContextRetrieverClient(
            "https://retriever.example.test/mcp",
            {"alex": "test-alex", "jordan": "test-jordan"},
            client=http,
        )
        tool = ToolDefinition(
            name="get_shipment_by_id",
            description="Generated shipment read",
            parameters={"type": "object"},
        )
        return client.call_tool("alex", tool, {"id": "SHIP-1002"})


@pytest.mark.parametrize("nested", [False, True])
def test_valid_shipment_is_returned_unchanged(nested: bool) -> None:
    record = shipment()
    result = retrieve(record, nested=nested)
    assert result == ({"results": [record]} if nested else record)


@pytest.mark.parametrize(
    "field,value",
    [
        ("shopper_id", "jordan"),
        ("status", "teleported"),
        ("fictional", False),
        ("fictional", 1),
        ("fictional", 1.0),
        ("original_eta", "2026-02-31"),
        ("estimated_delivery", "tomorrow"),
        ("updated_at", "2026-09-30T09:00:00"),
        ("latest_event", ""),
        ("shipment_id", ""),
        ("carrier", ""),
        ("order_id", ""),
    ],
)
def test_bad_shipments_are_rejected(field: str, value: object) -> None:
    record = shipment() | {field: value}
    with pytest.raises(ContextRetrieverError):
        retrieve(record, nested=True)


@pytest.mark.parametrize("field", ["shopper_id", "status", "fictional", "updated_at"])
def test_incomplete_shipments_are_rejected(field: str) -> None:
    record = shipment()
    del record[field]
    with pytest.raises(ContextRetrieverError):
        retrieve(record)


def test_demo_product_reaches_model_without_a_broken_catalogue_card() -> None:
    from app.shop.models import TurnContext
    from app.shop.tools import ShopRetrieval
    from tests.test_shop import make_shop

    record = {
        "product_id": "MIC-DEMO-01",
        "product_title": "RØDE VideoMicro II",
        "product_locale": "demo",
        "product_description": "Fictional demo product record",
    }

    class Retriever:
        def list_tools(self, shopper):
            return [
                ToolDefinition(
                    name="get_product_by_id",
                    description="Product reference",
                    parameters={"type": "object"},
                )
            ]

        def call_tool(self, shopper, tool, arguments):
            return record

    shop, _, _, _ = make_shop()
    shop.context_retriever = Retriever()
    context = TurnContext(message="My microphone delivery?", mode="none", shopper_id="alex")
    tools = ShopRetrieval(shop, "alex", context)
    assert tools.call("get_product_by_id", {"id": "MIC-DEMO-01"}) == record
    assert context.products == []
