"""Context Retriever contracts; service behaviour needs the separate live check."""

import json
import os
from datetime import date, datetime
from uuid import uuid4

import httpx
import pytest
from redis import Redis

pytest.importorskip("context_surfaces", reason="Install the context-retriever extra")

from app.catalog import Catalog  # noqa: E402
from app.settings import ROOT  # noqa: E402
from seed import shop_context  # noqa: E402


def smoke_module():
    from scripts import check_context_retriever

    return check_context_retriever


def test_fixtures_keep_source_product_json_and_fictional_purchase_links() -> None:
    fixtures = shop_context.load_fixtures()
    catalogue = Catalog.load(ROOT / "seed/cameras")
    assert len(fixtures.products) == len(fixtures.purchases) == len(fixtures.shipments) == 3
    assert len(fixtures.shoppers) == 2
    source_products = [
        product for product in fixtures.products if product.product_id != "MIC-DEMO-01"
    ]
    assert {product.product_id for product in source_products} == {"B09BBKVMCD", "B06XG9T25F"}
    for product in source_products:
        assert product.model_dump() == catalogue.products[product.product_id].model_dump()
    products = {product.product_id for product in fixtures.products}
    purchases = {purchase.order_id: purchase for purchase in fixtures.purchases}
    shipments = {shipment.shipment_id: shipment for shipment in fixtures.shipments}
    for shopper in fixtures.shoppers:
        assert shopper.fictional is True
        for order_id in shopper.purchase_ids:
            order = purchases[order_id]
            assert order.shopper_id == shopper.shopper_id
            assert order.product_id in products
            assert order.fictional is True
            shipment = shipments[order.shipment_id]
            assert shipment.shopper_id == shopper.shopper_id
            assert shipment.order_id == order.order_id
            assert shipment.fictional is True
            assert shipment.carrier == "Demo courier"
            assert shipment.status in {"in_transit", "delivered"}
            assert date.fromisoformat(shipment.original_eta)
            assert date.fromisoformat(shipment.estimated_delivery)
            assert datetime.fromisoformat(shipment.updated_at).tzinfo is not None
    documents = shop_context.fixture_documents(fixtures)
    assert len(documents) == 11
    assert all(key.startswith("camera:context-smoke:") for key in documents)


def test_delayed_microphone_order_is_explicitly_fictional_and_links_to_shipment() -> None:
    fixtures = shop_context.load_fixtures()
    alex = next(shopper for shopper in fixtures.shoppers if shopper.shopper_id == "alex")
    assert alex.purchase_ids == ["SAM-DEMO-1001", "SAM-DEMO-1002"]
    order = next(order for order in fixtures.purchases if order.order_id == "SAM-DEMO-1002")
    assert order.shopper_id == "alex"
    assert order.purchased_at == "2026-09-22"
    assert order.product_id == "MIC-DEMO-01"
    assert order.shipment_id == "SHIP-1002"
    microphone = next(
        product for product in fixtures.products if product.product_id == order.product_id
    )
    assert microphone.product_title == "RØDE VideoMicro II"
    assert "fictional demo product" in microphone.product_description.lower()
    assert microphone.product_bullet_point is None
    shipment = next(
        shipment for shipment in fixtures.shipments if shipment.shipment_id == order.shipment_id
    )
    assert shipment.model_dump() == {
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
    assert all(
        shipment.status == "delivered"
        for shipment in fixtures.shipments
        if shipment.shipment_id != "SHIP-1002"
    )


def test_legacy_documents_are_exact_original_six_records() -> None:
    catalogue = Catalog.load(ROOT / "seed/cameras")
    expected = {}
    for shopper_id, order_id, purchased_at, product_id in (
        ("alex", "SAM-DEMO-1001", "2026-04-18", "B09BBKVMCD"),
        ("jordan", "SAM-DEMO-2001", "2026-06-03", "B06XG9T25F"),
    ):
        expected[f"{shop_context.PREFIX}:product:{product_id}"] = catalogue.products[
            product_id
        ].model_dump()
        expected[f"{shop_context.PREFIX}:shopper:{shopper_id}"] = {
            "shopper_id": shopper_id,
            "display_name": shopper_id.title(),
            "fictional": True,
            "purchase_ids": [order_id],
        }
        expected[f"{shop_context.PREFIX}:purchase:{order_id}"] = {
            "order_id": order_id,
            "shopper_id": shopper_id,
            "product_id": product_id,
            "purchased_at": purchased_at,
            "fictional": True,
        }
    assert shop_context.legacy_fixture_documents() == expected


def test_export_declares_relationships_and_explicit_shopper_acl() -> None:
    model = shop_context.data_model()
    entities = {entity["name"]: entity for entity in model["entities"]}
    assert set(entities) == {"Shopper", "Purchase", "Product", "Shipment"}
    for name in ("Shopper", "Purchase", "Shipment"):
        assert entities[name]["acl_field_mappings"] == [
            {"document_field": "$.shopper_id", "access_tag": "shopper"}
        ]
    assert "acl_field_mappings" not in entities["Product"]
    links = {
        (entity["name"], relation["target"], relation["source_field"])
        for entity in entities.values()
        for relation in entity["relationships"]
    }
    assert links == {
        ("Shopper", "Purchase", "purchase_ids"),
        ("Purchase", "Shopper", "shopper_id"),
        ("Purchase", "Product", "product_id"),
        ("Purchase", "Shipment", "shipment_id"),
    }
    fields = {field["name"]: field for field in entities["Purchase"]["fields"]}
    assert fields["shopper_id"]["redis_indices"] == [{"type": "tag"}]
    assert fields["order_id"]["is_key_component"] is True
    assert all(field["type"] in {"str", "bool"} for field in fields.values())
    shipment_fields = {field["name"]: field for field in entities["Shipment"]["fields"]}
    assert set(shipment_fields) == {
        "shipment_id",
        "shopper_id",
        "order_id",
        "status",
        "carrier",
        "original_eta",
        "estimated_delivery",
        "latest_event",
        "updated_at",
        "fictional",
    }
    assert shipment_fields["shipment_id"]["is_key_component"] is True
    assert shipment_fields["shopper_id"]["redis_indices"] == [{"type": "tag"}]
    assert shipment_fields["order_id"]["redis_indices"] == [{"type": "tag"}]
    assert all(field["type"] in {"str", "bool"} for field in shipment_fields.values())
    # The live API rejects secondary indexes on primary-key components.
    assert all(
        not field["redis_indices"]
        for entity in entities.values()
        for field in entity["fields"]
        if field["is_key_component"]
    )


class MCPService:
    """A protocol fixture, not evidence of real Redis service isolation."""

    def __init__(self, fault: str = "") -> None:
        self.fault = fault
        self.fixtures = shop_context.load_fixtures()
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def respond(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        shopper = request.headers["X-API-Key"].removeprefix("fixture-")
        if body["method"] == "tools/list":
            names = {
                "get_shopper_by_id": {"id": {"type": "string"}},
                "get_purchase_by_id": {"id": {"type": "string"}},
                "get_product_by_id": {"id": {"type": "string"}},
                "get_shipment_by_id": {"id": {"type": "string"}},
                "filter_purchase": {
                    "tag_conditions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"enum": ["shopper_id", "product_id"]},
                                "value": {"type": "string"},
                            },
                            "required": ["field", "value"],
                            "additionalProperties": False,
                        },
                    },
                    "limit": {"type": "integer"},
                },
            }
            names["filter_shipment"] = names["filter_purchase"]
            tools = [
                {
                    "name": name,
                    "inputSchema": {
                        "type": "object",
                        "properties": fields,
                        "required": list(fields),
                        "additionalProperties": False,
                    },
                }
                for name, fields in names.items()
            ]
            if self.fault == "missing-tool":
                tools = [tool for tool in tools if tool["name"] != "get_purchase_by_id"]
            if self.fault == "missing-shipment-tool":
                tools = [tool for tool in tools if tool["name"] != "filter_shipment"]
            if self.fault == "schema-changed":
                tools[0]["inputSchema"]["required"].append("unexpected_parameter")
            result = {"tools": tools}
        else:
            name, args = body["params"]["name"], body["params"]["arguments"]
            self.calls.append((shopper, name, args))
            is_filter = name.startswith("filter_")
            if is_filter:
                source = (
                    self.fixtures.shipments
                    if name == "filter_shipment"
                    else self.fixtures.purchases
                )
                records = [
                    order
                    for order in source
                    if order.shopper_id == args["tag_conditions"][0]["value"]
                ]
            elif name == "get_purchase_by_id":
                records = [
                    order for order in self.fixtures.purchases if order.order_id == args["id"]
                ]
            elif name == "get_shopper_by_id":
                records = [
                    record for record in self.fixtures.shoppers if record.shopper_id == args["id"]
                ]
            elif name == "get_shipment_by_id":
                records = [
                    shipment
                    for shipment in self.fixtures.shipments
                    if shipment.shipment_id == args["id"]
                ]
            else:
                records = [
                    product
                    for product in self.fixtures.products
                    if product.product_id == args["id"]
                ]
            foreign = any(getattr(record, "shopper_id", shopper) != shopper for record in records)
            if self.fault != "leak" and not (self.fault == "shipment-leak" and "shipment" in name):
                records = [
                    record
                    for record in records
                    if getattr(record, "shopper_id", shopper) == shopper
                ]
            if self.fault in {"empty", "live-denial-no-control"}:
                records = []
            if (
                self.fault == "shipment-id-no-control"
                and name == "get_shipment_by_id"
                and args["id"] == "SHIP-1001"
            ):
                records = []
            if (
                self.fault == "purchase-id-no-control"
                and name == "get_purchase_by_id"
                and args["id"] == "SAM-DEMO-1001"
            ):
                records = []
            rows = [record.model_dump(mode="json") for record in records]
            if self.fault == f"partial-{name}" and is_filter:
                rows = rows[:1]
            if (
                self.fault == "duplicate-purchase-filter"
                and name == "filter_purchase"
                and len(rows) > 1
            ):
                rows = [rows[0], rows[0]]
            if self.fault == "reverse-filter" and is_filter:
                rows.reverse()
            if self.fault == "missing-shipment-field" and "shipment" in name:
                for row in rows:
                    row.pop("latest_event", None)
            if self.fault == "stale-shipment" and "shipment" in name:
                for row in rows:
                    if row["shipment_id"] == "SHIP-1002":
                        row["estimated_delivery"] = "2026-09-29"
            if self.fault == "missing-null-field":
                for row in rows:
                    if row.get("product_id") == "B09BBKVMCD":
                        row.pop("product_description", None)
            payload = {"results": rows} if is_filter else (rows[0] if rows else None)
            if self.fault == "error-with-empty-results" and foreign and is_filter:
                payload = {"results": [], "error": "Backend timeout"}
            if self.fault == "empty-object" and foreign and not is_filter:
                payload = {}
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
            if self.fault == "denial-error" and foreign:
                result = {"isError": True, "content": [{"type": "text", "text": "Denied"}]}
            if self.fault.startswith("live-denial") and foreign and not is_filter:
                entity = name.removeprefix("get_").removesuffix("_by_id")
                key = f"{shop_context.PREFIX}:{entity}:{args['id']}"
                if self.fault == "live-denial-wrong-id":
                    key += "-wrong"
                result = {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": "Error executing tool: get by ID failed: access denied: "
                            f"document not found: {key}",
                        }
                    ],
                }
                if self.fault == "live-denial-with-data":
                    result["structuredContent"] = {"shopper_id": "foreign"}
            if self.fault == "malformed":
                result = {"content": [{"type": "text", "text": "not JSON"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


def settings(**overrides):
    values = {
        "ctx_mcp_url": "https://context.example.test/mcp",
        "ctx_alex_agent_key": "fixture-alex",
        "ctx_jordan_agent_key": "fixture-jordan",
    }
    values.update(overrides)
    return smoke_module().SmokeSettings(_env_file=None, **values)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["", "reverse-filter"])
async def test_sdk_checks_positive_reads_and_foreign_filter_and_id_reads(fault: str) -> None:
    service = MCPService(fault)
    report = await smoke_module().run_smoke(
        settings(), transport=httpx.MockTransport(service.respond)
    )
    assert report.status == "passed"
    assert len(report.checks) == 27
    assert all(check.status == "passed" for check in report.checks)
    assert ("alex", "get_purchase_by_id", {"id": "SAM-DEMO-2001"}) in service.calls
    assert (
        "jordan",
        "filter_purchase",
        {"tag_conditions": [{"field": "shopper_id", "value": "alex"}], "limit": 10},
    ) in service.calls
    for shopper in service.fixtures.shoppers:
        for purchase in service.fixtures.purchases:
            assert (
                shopper.shopper_id,
                "get_purchase_by_id",
                {"id": purchase.order_id},
            ) in service.calls
            if purchase.shopper_id == shopper.shopper_id:
                assert (
                    shopper.shopper_id,
                    "get_product_by_id",
                    {"id": purchase.product_id},
                ) in service.calls
        for shipment in service.fixtures.shipments:
            assert (
                shopper.shopper_id,
                "get_shipment_by_id",
                {"id": shipment.shipment_id},
            ) in service.calls
        for filtered_shopper in service.fixtures.shoppers:
            assert (
                shopper.shopper_id,
                "filter_shipment",
                {
                    "tag_conditions": [
                        {"field": "shopper_id", "value": filtered_shopper.shopper_id}
                    ],
                    "limit": 10,
                },
            ) in service.calls
    shipment_filter = next(check for check in report.checks if check.name == "alex:shipment-filter")
    assert set(shipment_filter.returned_ids) == {"SHIP-1001", "SHIP-1002"}
    assert "fixture-alex" not in report.model_dump_json()


@pytest.mark.asyncio
async def test_observed_explicit_id_denial_passes_with_successful_controls() -> None:
    service = MCPService("live-denial")
    report = await smoke_module().run_smoke(
        settings(), transport=httpx.MockTransport(service.respond)
    )
    assert report.status == "passed"
    assert len(report.checks) == 27
    denied = [
        check for check in report.checks if "foreign" in check.name and "filter" not in check.name
    ]
    assert len(denied) == 8
    assert all(check.status == "passed" and "denied" in check.detail for check in denied)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault",
    [
        "leak",
        "empty",
        "missing-tool",
        "malformed",
        "denial-error",
        "schema-changed",
        "missing-null-field",
        "error-with-empty-results",
        "empty-object",
        "live-denial-wrong-id",
        "live-denial-with-data",
        "live-denial-no-control",
        "partial-filter_purchase",
        "partial-filter_shipment",
        "duplicate-purchase-filter",
        "missing-shipment-tool",
        "missing-shipment-field",
        "shipment-leak",
        "stale-shipment",
        "shipment-id-no-control",
        "purchase-id-no-control",
    ],
)
async def test_incomplete_or_leaking_service_cannot_pass(fault: str) -> None:
    service = MCPService(fault)
    report = await smoke_module().run_smoke(
        settings(), transport=httpx.MockTransport(service.respond)
    )
    assert report.status != "passed"
    if fault in {"empty", "live-denial-no-control"}:
        assert all(
            check.status == "inconclusive" for check in report.checks if "foreign" in check.name
        )
    if fault == "schema-changed":
        assert not any(name == "get_shopper_by_id" for _, name, _ in service.calls)
    affected_checks = {
        "partial-filter_purchase": "alex:purchase-filter",
        "partial-filter_shipment": "alex:shipment-filter",
        "duplicate-purchase-filter": "alex:purchase-filter",
        "missing-shipment-tool": "alex:shipment-filter",
        "missing-shipment-field": "alex:shipment-filter",
        "shipment-leak": "alex:foreign-shipment-filter",
        "stale-shipment": "alex:shipment-filter",
    }
    if fault in affected_checks:
        affected = [check for check in report.checks if check.name == affected_checks[fault]]
        assert len(affected) == 1
        assert affected[0].status != "passed"
    if fault in {"shipment-id-no-control", "purchase-id-no-control"}:
        entity = fault.split("-")[0]
        foreign_checks = [
            check for check in report.checks if check.name.startswith(f"alex:foreign-{entity}-id")
        ]
        assert foreign_checks
        assert all(check.status == "inconclusive" for check in foreign_checks)


@pytest.mark.asyncio
async def test_shared_agent_key_is_rejected_before_network_access() -> None:
    service = MCPService()
    with pytest.raises(smoke_module().SmokeError, match="distinct"):
        await smoke_module().run_smoke(
            settings(ctx_jordan_agent_key="fixture-alex"),
            transport=httpx.MockTransport(service.respond),
        )
    assert not service.calls


@pytest.mark.skipif(not os.getenv("TEST_REDIS_URL"), reason="Set TEST_REDIS_URL")
@pytest.mark.parametrize("conflicting_value", [{"different": True}, None])
def test_json_seed_roundtrip_is_repeatable_and_rejects_conflicts(conflicting_value) -> None:
    module = smoke_module()
    documents = {
        f"test_context_{uuid4().hex}:{i}": body
        for i, body in enumerate(
            shop_context.fixture_documents(shop_context.load_fixtures()).values()
        )
    }
    with Redis.from_url(os.environ["TEST_REDIS_URL"]) as client:
        try:
            assert module.seed_documents(client, documents) == 11
            assert module.seed_documents(client, documents) == 0
            assert {key: client.json().get(key) for key in documents} == documents
            key = next(iter(documents))
            client.json().set(key, "$", conflicting_value)
            with pytest.raises(module.SmokeError, match="different"):
                module.seed_documents(client, documents)
            assert client.json().get(key) == conflicting_value
            assert client.exists(key)
        finally:
            client.delete(*documents)
