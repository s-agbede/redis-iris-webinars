"""Eleven isolated JSON fixtures and the official Context Retriever entity model."""

from typing import ClassVar

from context_surfaces.context_model import (
    ContextField,
    ContextModel,
    ContextRelationship,
    export_data_model,
)
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from app.catalog import Catalog
from app.settings import ROOT

PREFIX = "camera:context-smoke"


class Product(ContextModel):
    """Source or explicit demo listing; price, stock and compatibility are not verified."""

    model_config = ConfigDict(extra="forbid", strict=True)
    __redis_key_template__ = f"{PREFIX}:product:{{product_id}}"

    product_id: str = ContextField(description="Source product ID", is_key_component=True)
    product_title: str = ContextField(description="Original product title", index="text")
    product_description: str | None = ContextField(description="Source description", default=None)
    product_bullet_point: str | None = ContextField(
        description="Source bullet points", default=None
    )
    product_brand: str | None = ContextField(description="Source brand", index="tag", default=None)
    product_color: str | None = ContextField(description="Source colour", default=None)
    product_locale: str = ContextField(description="Source marketplace", default="us")


class Shopper(ContextModel):
    """Fictional shopper whose records require a matching shopper access tag."""

    model_config = ConfigDict(extra="forbid", strict=True)
    __redis_key_template__ = f"{PREFIX}:shopper:{{shopper_id}}"
    __acl_field_mappings__: ClassVar[list[dict[str, str]]] = [
        {"document_field": "$.shopper_id", "access_tag": "shopper"}
    ]

    shopper_id: str = ContextField(description="Demo shopper ID", is_key_component=True)
    display_name: str = ContextField(description="Fictional display name")
    fictional: bool = ContextField(description="This is a fictional demo shopper", default=True)
    purchase_ids: list[str] = ContextField(description="Historical demo purchase IDs")
    purchases: ClassVar[ContextRelationship] = ContextRelationship(
        description="Historical purchases, not proof of current ownership",
        target="Purchase",
        source_field="purchase_ids",
    )


class Purchase(ContextModel):
    """Fictional purchase linked to a source or explicit demo product and shipment."""

    model_config = ConfigDict(extra="forbid", strict=True)
    __redis_key_template__ = f"{PREFIX}:purchase:{{order_id}}"
    __acl_field_mappings__: ClassVar[list[dict[str, str]]] = [
        {"document_field": "$.shopper_id", "access_tag": "shopper"}
    ]

    order_id: str = ContextField(description="Demo order ID", is_key_component=True)
    shopper_id: str = ContextField(description="Purchasing shopper", index="tag")
    product_id: str = ContextField(description="Source catalogue product ID", index="tag")
    shipment_id: str = ContextField(description="Fictional shipment ID")
    purchased_at: str = ContextField(description="Fictional purchase date, YYYY-MM-DD")
    fictional: bool = ContextField(description="This is a fictional transaction", default=True)
    shopper: ClassVar[ContextRelationship] = ContextRelationship(
        description="Shopper who placed the order", target="Shopper", source_field="shopper_id"
    )
    product: ClassVar[ContextRelationship] = ContextRelationship(
        description="Purchased catalogue product", target="Product", source_field="product_id"
    )
    shipment: ClassVar[ContextRelationship] = ContextRelationship(
        description="Fictional delivery record", target="Shipment", source_field="shipment_id"
    )


class Shipment(ContextModel):
    """Fictional delivery record isolated by its shopper access tag."""

    model_config = ConfigDict(extra="forbid", strict=True)
    __redis_key_template__ = f"{PREFIX}:shipment:{{shipment_id}}"
    __acl_field_mappings__: ClassVar[list[dict[str, str]]] = [
        {"document_field": "$.shopper_id", "access_tag": "shopper"}
    ]

    shipment_id: str = ContextField(description="Demo shipment ID", is_key_component=True)
    shopper_id: str = ContextField(description="Receiving shopper", index="tag")
    order_id: str = ContextField(description="Associated demo order ID", index="tag")
    status: str = ContextField(description="Fictional status: in_transit or delivered")
    carrier: str = ContextField(description="Fictional courier name")
    original_eta: str = ContextField(description="Original fictional delivery date, YYYY-MM-DD")
    estimated_delivery: str = ContextField(
        description="Current fictional delivery date, YYYY-MM-DD"
    )
    latest_event: str = ContextField(description="Latest fictional shipment event")
    updated_at: str = ContextField(description="Fictional update time, timezone-aware ISO datetime")
    fictional: bool = ContextField(description="This is a fictional shipment", default=True)


class Fixtures(BaseModel):
    products: list[Product]
    shoppers: list[Shopper]
    purchases: list[Purchase]
    shipments: list[Shipment]


def load_fixtures() -> Fixtures:
    """Preserve two source products and add one clearly fictional delivery scenario."""
    catalogue = Catalog.load(ROOT / "seed/cameras")
    purchases = [
        Purchase(
            order_id="SAM-DEMO-1001",
            shopper_id="alex",
            purchased_at="2026-04-18",
            product_id="B09BBKVMCD",
            shipment_id="SHIP-1001",
        ),
        Purchase(
            order_id="SAM-DEMO-1002",
            shopper_id="alex",
            purchased_at="2026-09-22",
            product_id="MIC-DEMO-01",
            shipment_id="SHIP-1002",
        ),
        Purchase(
            order_id="SAM-DEMO-2001",
            shopper_id="jordan",
            purchased_at="2026-06-03",
            product_id="B06XG9T25F",
            shipment_id="SHIP-2001",
        ),
    ]
    return Fixtures(
        purchases=purchases,
        products=[
            *[
                Product.model_validate(catalogue.products[product_id].model_dump())
                for product_id in ("B09BBKVMCD", "B06XG9T25F")
            ],
            Product(
                product_id="MIC-DEMO-01",
                product_title="RØDE VideoMicro II",
                product_description=(
                    "Fictional demo product record for the delivery scenario; "
                    "not a verified catalogue listing or specification."
                ),
                product_locale="demo",
            ),
        ],
        shoppers=[
            Shopper(
                shopper_id=shopper_id,
                display_name=shopper_id.title(),
                purchase_ids=[
                    order.order_id for order in purchases if order.shopper_id == shopper_id
                ],
            )
            for shopper_id in ("alex", "jordan")
        ],
        shipments=[
            Shipment(
                shipment_id="SHIP-1001",
                shopper_id="alex",
                order_id="SAM-DEMO-1001",
                status="delivered",
                carrier="Demo courier",
                original_eta="2026-04-22",
                estimated_delivery="2026-04-22",
                latest_event="Delivered",
                updated_at="2026-04-22T14:00:00Z",
            ),
            Shipment(
                shipment_id="SHIP-1002",
                shopper_id="alex",
                order_id="SAM-DEMO-1002",
                status="in_transit",
                carrier="Demo courier",
                original_eta="2026-09-29",
                estimated_delivery="2026-10-01",
                latest_event="Held at local depot",
                updated_at="2026-09-30T09:00:00Z",
            ),
            Shipment(
                shipment_id="SHIP-2001",
                shopper_id="jordan",
                order_id="SAM-DEMO-2001",
                status="delivered",
                carrier="Demo courier",
                original_eta="2026-06-07",
                estimated_delivery="2026-06-06",
                latest_event="Delivered",
                updated_at="2026-06-06T11:30:00Z",
            ),
        ],
    )


def data_model() -> dict[str, JsonValue]:
    return TypeAdapter(dict[str, JsonValue]).validate_python(
        export_data_model(
            title="Camera shop smoke test",
            description=(
                "Shared source and explicit demo products with isolated fictional shoppers, "
                "purchases and shipments."
            ),
            entities=[Shopper, Purchase, Product, Shipment],
        )
    )


def fixture_documents(fixtures: Fixtures) -> dict[str, dict[str, JsonValue]]:
    """Use the same key templates that the service will read."""
    records: list[ContextModel] = [
        *fixtures.products,
        *fixtures.shoppers,
        *fixtures.purchases,
        *fixtures.shipments,
    ]
    documents: dict[str, dict[str, JsonValue]] = {}
    for record in records:
        template = record.__redis_key_template__
        if template is None:
            raise ValueError("A fixture has no Redis key template.")
        body = record.model_dump(mode="json")
        documents[template.format(**body)] = TypeAdapter(dict[str, JsonValue]).validate_python(body)
    return documents


def legacy_fixture_documents() -> dict[str, dict[str, JsonValue]]:
    """Derive the original six exact JSON values for a guarded, explicit migration."""
    documents = fixture_documents(load_fixtures())
    legacy: dict[str, dict[str, JsonValue]] = {}
    for shopper_id, order_id, product_id in (
        ("alex", "SAM-DEMO-1001", "B09BBKVMCD"),
        ("jordan", "SAM-DEMO-2001", "B06XG9T25F"),
    ):
        product_key = f"{PREFIX}:product:{product_id}"
        legacy[product_key] = documents[product_key]
        shopper_key = f"{PREFIX}:shopper:{shopper_id}"
        legacy[shopper_key] = {**documents[shopper_key], "purchase_ids": [order_id]}
        purchase_key = f"{PREFIX}:purchase:{order_id}"
        legacy[purchase_key] = {
            key: value for key, value in documents[purchase_key].items() if key != "shipment_id"
        }
    return legacy
