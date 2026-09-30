"""Discover and call Redis Context Retriever tools with shopper-scoped credentials."""

import json
import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Literal
from uuid import uuid4

import httpx
from jsonschema import SchemaError
from jsonschema import ValidationError as SchemaValidationError
from jsonschema.validators import validator_for
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, field_validator
from referencing import Registry
from referencing.exceptions import Unresolvable

from app.shop.models import ShopperID, ToolDefinition

UNAVAILABLE = "Context Retriever is unavailable. Please try again shortly."


class ContextRetrieverError(RuntimeError):
    """A credential-free retrieval failure safe to show to the shopper."""


class PurchaseRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    order_id: str = Field(min_length=1)
    shopper_id: ShopperID
    product_id: str = Field(min_length=1)
    purchased_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    fictional: Literal[True]

    @field_validator("fictional", mode="before")
    @classmethod
    def explicitly_fictional(cls, value: object) -> Literal[True]:
        if value is not True:
            raise ValueError("A demo record requires fictional=true.")
        return True

    @field_validator("purchased_at")
    @classmethod
    def valid_purchase_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value


class ShipmentRecord(BaseModel):
    """Dated, shopper-owned demo delivery evidence returned by generated tools."""

    model_config = ConfigDict(extra="ignore", strict=True)

    shipment_id: str = Field(min_length=1)
    order_id: str = Field(min_length=1)
    shopper_id: ShopperID
    status: Literal["in_transit", "delivered"]
    carrier: str = Field(min_length=1)
    original_eta: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    estimated_delivery: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    latest_event: str = Field(min_length=1)
    updated_at: str
    fictional: Literal[True]

    @field_validator("fictional", mode="before")
    @classmethod
    def explicitly_fictional(cls, value: object) -> Literal[True]:
        return PurchaseRecord.explicitly_fictional(value)

    @field_validator("original_eta", "estimated_delivery")
    @classmethod
    def valid_date(cls, value: str) -> str:
        date.fromisoformat(value)
        return value

    @field_validator("updated_at")
    @classmethod
    def timezone_required(cls, value: str) -> str:
        if datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError("Shipment updates require a timezone.")
        return value


class DemoProductRecord(BaseModel):
    """Order reference evidence without a corresponding purchasable catalogue page."""

    model_config = ConfigDict(extra="ignore", strict=True)
    product_id: str = Field(min_length=1)
    product_title: str = Field(min_length=1)
    product_description: str = Field(min_length=1)
    product_locale: Literal["demo"]


class MCPTool(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str
    description: str = ""
    inputSchema: dict[str, JsonValue]


class ToolPage(BaseModel):
    model_config = ConfigDict(strict=True)

    tools: list[MCPTool]
    nextCursor: str | None = None


class TextContent(BaseModel):
    model_config = ConfigDict(strict=True)

    type: Literal["text"]
    text: str


class ToolResult(BaseModel):
    model_config = ConfigDict(strict=True)

    isError: bool = False
    content: list[TextContent] = Field(default_factory=list)
    structuredContent: JsonValue = None


class ToolResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    jsonrpc: Literal["2.0"]
    id: str
    result: dict[str, JsonValue] | None = None
    error: dict[str, JsonValue] | None = None


def _query_error_feedback(result: ToolResult) -> dict[str, JsonValue] | None:
    """Expose known query outcomes without echoing upstream text or record keys."""
    if len(result.content) != 1 or result.structuredContent is not None:
        return None
    message = result.content[0].text
    if re.match(
        r"^Error executing tool: tag_conditions\[\d+\] names a field "
        r"[A-Za-z_][A-Za-z0-9_]* does not have as a tag field:",
        message,
    ):
        return {
            "isError": True,
            "error": "invalid_filter_field",
            "message": (
                "This entity cannot filter on the selected TAG field. "
                "Use only indexed fields from the tool descriptions, "
                "an ID lookup, or another declared relationship. "
                "The query failed; this is not an empty result."
            ),
        }
    if re.fullmatch(
        r"Error executing tool: get by ID failed: (?:access denied: )?"
        r"document not found: [^\r\n]+",
        message,
    ):
        return {
            "isError": True,
            "error": "record_unavailable",
            "message": (
                "No accessible record was returned for this ID. It may not exist "
                "or may be outside this shopper's access; do not infer which. "
                "Do not guess other IDs or change the shopper."
            ),
        }
    return None


class ContextRetrieverClient:
    """Use one connection pool, selecting credentials per request, never globally."""

    def __init__(
        self,
        mcp_url: str,
        keys: Mapping[ShopperID, str],
        *,
        client: httpx.Client | None = None,
    ) -> None:
        if set(keys) != {"alex", "jordan"} or any(not key.strip() for key in keys.values()):
            raise ContextRetrieverError("Configure a Context Retriever key for each demo shopper.")
        if keys["alex"] == keys["jordan"]:
            raise ContextRetrieverError("Context Retriever requires distinct shopper-scoped keys.")
        try:
            endpoint = httpx.URL(mcp_url)
        except httpx.InvalidURL:
            raise ContextRetrieverError("Configure the HTTPS Context Retriever endpoint.") from None
        if endpoint.scheme != "https" or not endpoint.host:
            raise ContextRetrieverError("Configure the HTTPS Context Retriever endpoint.")
        self._url = mcp_url
        self._keys = dict(keys)
        self._client = client or httpx.Client(timeout=20)

    def close(self) -> None:
        self._client.close()

    def _rpc(
        self, shopper_id: ShopperID, method: str, params: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        if shopper_id not in self._keys:
            raise ContextRetrieverError("Choose a valid demo shopper for Context Retriever.")
        request_id = uuid4().hex
        try:
            response = self._client.post(
                self._url,
                headers={"X-API-Key": self._keys[shopper_id]},
                json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            )
            response.raise_for_status()
            envelope = ToolResponse.model_validate(response.json())
            if envelope.id != request_id or envelope.error is not None or envelope.result is None:
                raise ContextRetrieverError(UNAVAILABLE)
            return envelope.result
        except (httpx.HTTPError, ValueError):
            raise ContextRetrieverError(UNAVAILABLE) from None

    def list_tools(self, shopper_id: ShopperID) -> list[ToolDefinition]:
        """Discover anew for this shopper; never share credential-dependent tool lists."""
        definitions: dict[str, ToolDefinition] = {}
        cursors: set[str] = set()
        params: dict[str, JsonValue] = {}
        try:
            for _ in range(10):
                page = ToolPage.model_validate(self._rpc(shopper_id, "tools/list", params))
                for tool in page.tools:
                    if tool.name in definitions or tool.inputSchema.get("type") != "object":
                        raise ContextRetrieverError(UNAVAILABLE)
                    validator_for(tool.inputSchema).check_schema(tool.inputSchema)
                    definitions[tool.name] = ToolDefinition(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.inputSchema,
                    )
                if not page.nextCursor:
                    if not definitions:
                        raise ContextRetrieverError(UNAVAILABLE)
                    return list(definitions.values())
                if page.nextCursor in cursors:
                    raise ContextRetrieverError(UNAVAILABLE)
                cursors.add(page.nextCursor)
                params = {"cursor": page.nextCursor}
        except (ValueError, SchemaError):
            raise ContextRetrieverError(UNAVAILABLE) from None
        raise ContextRetrieverError(UNAVAILABLE)

    def call_tool(
        self, shopper_id: ShopperID, tool: ToolDefinition, arguments: dict[str, JsonValue]
    ) -> JsonValue:
        """Execute exactly the generated tool the model selected, without hidden follow-up reads."""
        try:
            # Resolve local definitions only; tool schemas must not trigger extra network reads.
            validator_for(tool.parameters)(tool.parameters, registry=Registry()).validate(arguments)
        except SchemaValidationError:
            raise ContextRetrieverError(
                "The adviser supplied invalid Context Retriever tool arguments."
            ) from None
        except Unresolvable:
            raise ContextRetrieverError(UNAVAILABLE) from None
        try:
            result = ToolResult.model_validate(
                self._rpc(shopper_id, "tools/call", {"name": tool.name, "arguments": arguments})
            )
            if result.isError:
                if feedback := _query_error_feedback(result):
                    return feedback
                raise ContextRetrieverError(UNAVAILABLE)
            if result.structuredContent is not None:
                payload = result.structuredContent
            elif len(result.content) == 1:
                payload = TypeAdapter(JsonValue).validate_python(json.loads(result.content[0].text))
            else:
                raise ContextRetrieverError(UNAVAILABLE)
            self._validate_records(shopper_id, payload)
            return payload
        except ValueError:
            raise ContextRetrieverError(UNAVAILABLE) from None

    @staticmethod
    def _validate_records(shopper_id: ShopperID, payload: JsonValue) -> None:
        # Access tags enforce scope at the service. Reject any foreign record before
        # passing it to the model as a second check, including relationship results.
        if isinstance(payload, dict):
            if "error" in payload or (
                "shopper_id" in payload and payload["shopper_id"] != shopper_id
            ):
                raise ContextRetrieverError(UNAVAILABLE)
            if "shipment_id" in payload and "purchased_at" not in payload:
                ShipmentRecord.model_validate(payload)
            elif "order_id" in payload:
                PurchaseRecord.model_validate(payload)
            if payload.get("product_locale") == "demo":
                DemoProductRecord.model_validate(payload)
            for value in payload.values():
                ContextRetrieverClient._validate_records(shopper_id, value)
        elif isinstance(payload, list):
            for item in payload:
                ContextRetrieverClient._validate_records(shopper_id, item)
