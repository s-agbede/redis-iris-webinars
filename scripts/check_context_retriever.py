"""Export, seed and check an isolated Context Retriever surface without an LLM."""

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from typing import Literal, cast

import httpx
from context_surfaces.context_model import ContextModel
from context_surfaces.exceptions import MCPError
from context_surfaces.mcp_client import MCPClient
from jsonschema import SchemaError
from jsonschema import ValidationError as SchemaValidationError
from jsonschema.validators import validator_for
from pydantic import BaseModel, Field, JsonValue, SecretStr, TypeAdapter, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis import Redis
from redis.exceptions import RedisError, WatchError

from app.settings import ROOT
from seed.shop_context import PREFIX, Fixtures, data_model, fixture_documents, load_fixtures

Status = Literal["passed", "failed", "inconclusive"]


class SmokeError(RuntimeError):
    """An actionable error that contains no credentials or upstream response text."""


class SmokeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    ctx_redis_url: SecretStr = SecretStr("")
    ctx_mcp_url: str = ""
    ctx_alex_agent_key: SecretStr = SecretStr("")
    ctx_jordan_agent_key: SecretStr = SecretStr("")
    ctx_timeout_seconds: float = Field(default=20, gt=0, le=60)

    def agent_keys(self) -> dict[str, str]:
        values = {
            "alex": self.ctx_alex_agent_key.get_secret_value(),
            "jordan": self.ctx_jordan_agent_key.get_secret_value(),
        }
        missing = [f"CTX_{name.upper()}_AGENT_KEY" for name, value in values.items() if not value]
        if not self.ctx_mcp_url:
            missing.append("CTX_MCP_URL")
        if missing:
            raise SmokeError("Configure " + ", ".join(missing) + " to run the live check.")
        if values["alex"] == values["jordan"]:
            raise SmokeError("Use distinct agent keys scoped to Alex and Jordan.")
        return values


class ToolDefinition(BaseModel):
    name: str
    description: str = ""
    inputSchema: dict[str, JsonValue]


class Check(BaseModel):
    name: str
    tool: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    status: Status = "inconclusive"
    detail: str = "Not checked."
    returned_ids: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0


class Report(BaseModel):
    checked_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    sdk_version: str = Field(default_factory=lambda: version("redis-context-retriever"))
    status: Status = "inconclusive"
    tools: dict[str, list[ToolDefinition]] = Field(default_factory=dict)
    checks: list[Check] = Field(default_factory=list)
    scope: str = (
        "Reads eleven isolated JSON fixtures through generated MCP tools. Checks source and "
        "demo product fields, every purchase and shipment, and shopper isolation on filter "
        "and ID lookups. Does not "
        "verify generated relationship-tool traversal, chat answers, or production authentication."
    )


def same_json(left: JsonValue, right: JsonValue) -> bool:
    """Compare JSON values without treating boolean true as numeric one."""
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def seed_documents(client: Redis, documents: dict[str, dict[str, JsonValue]]) -> int:
    """Create missing fixtures atomically; refuse any existing value that differs."""
    with client.pipeline() as pipe:
        try:
            # redis-py's synchronous WATCH method currently lacks annotations.
            pipe.watch(*documents)  # type: ignore[no-untyped-call]
            missing: list[str] = []
            for key, body in documents.items():
                existing = cast(dict[str, JsonValue] | None, pipe.json().get(key))
                if existing is None and not pipe.exists(key):
                    missing.append(key)
                elif not same_json(existing, body):
                    raise SmokeError(
                        f"Fixture {key} already contains different data; nothing written."
                    )
            pipe.multi()
            for key in missing:
                pipe.execute_command(  # type: ignore[no-untyped-call]
                    "JSON.SET", key, "$", json.dumps(documents[key]), "NX"
                )
            written = pipe.execute()
            if len(written) != len(missing) or not all(written):
                raise SmokeError(
                    "A fixture write was not acknowledged; inspect the stored records."
                )
            return len(missing)
        except WatchError:
            raise SmokeError("Fixture data changed during seeding; inspect and retry.") from None


def result_rows(raw: object, *, filtered: bool) -> list[dict[str, JsonValue]]:
    """Accept documented MCP JSON results; a tool error is never an empty success."""
    if not isinstance(raw, dict) or raw.get("isError"):
        raise SmokeError("The tool reported an error; access denial has not been established.")
    if "structuredContent" in raw and raw["structuredContent"] is not None:
        payload = raw["structuredContent"]
    else:
        content = raw.get("content")
        if not isinstance(content, list) or len(content) != 1:
            raise SmokeError("Unexpected MCP content; inspect the service response format.")
        block = content[0]
        if not isinstance(block, dict) or block.get("type") != "text":
            raise SmokeError("Expected a JSON text tool result.")
        text = block.get("text")
        if not isinstance(text, str):
            raise SmokeError("Expected a JSON text tool result.")
        try:
            payload = json.loads(text)
        except ValueError:
            raise SmokeError("The tool did not return valid JSON.") from None
    if isinstance(payload, dict) and "error" in payload:
        raise SmokeError("The result contains an error; it cannot establish a successful read.")
    if filtered:
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise SmokeError("Expected the filter tool's results array.")
        rows = payload["results"]
    elif payload is None:
        rows = []
    elif isinstance(payload, dict) and payload:
        rows = [payload]
    else:
        raise SmokeError("Expected an entity or a null ID lookup result.")
    try:
        return TypeAdapter(list[dict[str, JsonValue]]).validate_python(rows, strict=True)
    except ValidationError:
        raise SmokeError("The tool returned malformed records.") from None


def explicit_id_denial(raw: object, check: Check) -> bool:
    """Recognize the observed live denial only for the exact requested fixture key."""
    entity = {
        "get_shopper_by_id": "shopper",
        "get_purchase_by_id": "purchase",
        "get_shipment_by_id": "shipment",
    }.get(check.tool)
    record_id = check.arguments.get("id")
    if entity is None or not isinstance(record_id, str):
        return False
    return raw == {
        "isError": True,
        "content": [
            {
                "type": "text",
                "text": "Error executing tool: get by ID failed: access denied: "
                f"document not found: {PREFIX}:{entity}:{record_id}",
            }
        ],
    }


async def probe(
    client: MCPClient,
    definitions: dict[str, ToolDefinition],
    check: Check,
    expected: list[dict[str, JsonValue]] | None,
    *,
    control_passed: bool = True,
) -> Check:
    started = perf_counter()
    try:
        definition = definitions.get(check.tool)
        if definition is None:
            raise SmokeError("Required generated tool is missing.")
        validator = validator_for(definition.inputSchema)
        try:
            validator.check_schema(definition.inputSchema)
            validator(definition.inputSchema).validate(check.arguments)
        except (SchemaError, SchemaValidationError):
            raise SmokeError(
                "Generated tool schema differs from the expected read contract."
            ) from None
        raw = await client.call_tool(check.tool, check.arguments)
        if expected is None and explicit_id_denial(raw, check):
            if control_passed:
                check.status = "passed"
                check.detail = "Service explicitly denied this ID; permitted read also passed."
            else:
                check.detail = "Explicit denial is inconclusive because the permitted read failed."
            return check
        rows = result_rows(raw, filtered=check.tool.startswith("filter_"))
        id_field = {
            "get_shopper_by_id": "shopper_id",
            "get_product_by_id": "product_id",
            "get_purchase_by_id": "order_id",
            "filter_purchase": "order_id",
            "get_shipment_by_id": "shipment_id",
            "filter_shipment": "shipment_id",
        }.get(check.tool, "id")
        check.returned_ids = [str(row.get(id_field, "unknown")) for row in rows]
        if expected is None:
            if rows:
                check.status, check.detail = "failed", "Another shopper's read returned data."
            elif not control_passed:
                check.detail = (
                    "Empty result is inconclusive because the permitted read did not pass."
                )
            else:
                check.status, check.detail = (
                    "passed",
                    "No foreign record; permitted read also passed.",
                )
        else:
            unmatched = list(rows)
            for record in expected:
                match = next(
                    (
                        index
                        for index, row in enumerate(unmatched)
                        if all(
                            key in row and same_json(row[key], value)
                            for key, value in record.items()
                        )
                    ),
                    None,
                )
                if match is None:
                    break
                unmatched.pop(match)
            else:
                if not unmatched:
                    check.status = "passed"
                    check.detail = "All returned records and fields match the expected fixtures."
            if check.status != "passed":
                check.status, check.detail = (
                    "failed",
                    "Permitted read did not return every expected fixture exactly once.",
                )
    except SmokeError as exc:
        check.detail = str(exc)
    except MCPError:
        check.detail = "MCP request failed. Check endpoint, agent key and service readiness."
    finally:
        check.elapsed_ms = round((perf_counter() - started) * 1000, 2)
    return check


async def check_shopper(
    client: MCPClient, shopper_id: str, fixtures: Fixtures, report: Report
) -> None:
    try:
        tools = TypeAdapter(list[ToolDefinition]).validate_python(await client.list_tools())
    except (MCPError, ValidationError):
        report.checks.append(
            Check(
                name=f"{shopper_id}:discovery",
                tool="tools/list",
                detail="Tool discovery failed. Check endpoint, credentials and returned schemas.",
            )
        )
        return
    report.tools[shopper_id] = tools
    definitions = {tool.name: tool for tool in tools}
    shopper = next(row for row in fixtures.shoppers if row.shopper_id == shopper_id)
    purchases = [row for row in fixtures.purchases if row.shopper_id == shopper_id]
    shipments = [row for row in fixtures.shipments if row.shopper_id == shopper_id]
    reads: list[tuple[str, str, dict[str, JsonValue], list[ContextModel]]] = [
        ("shopper", "get_shopper_by_id", {"id": shopper_id}, [shopper]),
        (
            "purchase-filter",
            "filter_purchase",
            {"tag_conditions": [{"field": "shopper_id", "value": shopper_id}], "limit": 10},
            list(purchases),
        ),
        (
            "shipment-filter",
            "filter_shipment",
            {"tag_conditions": [{"field": "shopper_id", "value": shopper_id}], "limit": 10},
            list(shipments),
        ),
    ]
    for purchase in purchases:
        product = next(row for row in fixtures.products if row.product_id == purchase.product_id)
        reads.extend(
            [
                (
                    f"purchase-id:{purchase.order_id}",
                    "get_purchase_by_id",
                    {"id": purchase.order_id},
                    [purchase],
                ),
                (
                    f"product:{product.product_id}",
                    "get_product_by_id",
                    {"id": product.product_id},
                    [product],
                ),
            ]
        )
    for shipment in shipments:
        reads.append(
            (
                f"shipment-id:{shipment.shipment_id}",
                "get_shipment_by_id",
                {"id": shipment.shipment_id},
                [shipment],
            )
        )
    controls: dict[str, bool] = {}
    for label, tool, arguments, records in reads:
        check = await probe(
            client,
            definitions,
            Check(
                name=f"{shopper_id}:{label}",
                tool=tool,
                arguments=arguments,
            ),
            [record.model_dump(mode="json") for record in records],
        )
        report.checks.append(check)
        controls[tool] = controls.get(tool, True) and check.status == "passed"
    foreign_reads: list[tuple[str, str, dict[str, JsonValue]]] = []
    for foreign in fixtures.shoppers:
        if foreign.shopper_id == shopper_id:
            continue
        foreign_reads.append(("foreign-shopper", "get_shopper_by_id", {"id": foreign.shopper_id}))
        for entity in ("purchase", "shipment"):
            foreign_reads.append(
                (
                    f"foreign-{entity}-filter",
                    f"filter_{entity}",
                    {
                        "tag_conditions": [{"field": "shopper_id", "value": foreign.shopper_id}],
                        "limit": 10,
                    },
                )
            )
    for purchase in fixtures.purchases:
        if purchase.shopper_id != shopper_id:
            foreign_reads.append(
                (
                    f"foreign-purchase-id:{purchase.order_id}",
                    "get_purchase_by_id",
                    {"id": purchase.order_id},
                )
            )
    for shipment in fixtures.shipments:
        if shipment.shopper_id != shopper_id:
            foreign_reads.append(
                (
                    f"foreign-shipment-id:{shipment.shipment_id}",
                    "get_shipment_by_id",
                    {"id": shipment.shipment_id},
                )
            )
    for label, tool, arguments in foreign_reads:
        report.checks.append(
            await probe(
                client,
                definitions,
                Check(
                    name=f"{shopper_id}:{label}",
                    tool=tool,
                    arguments=arguments,
                ),
                None,
                control_passed=controls[tool],
            )
        )


async def run_smoke(
    settings: SmokeSettings, *, transport: httpx.AsyncBaseTransport | None = None
) -> Report:
    keys = settings.agent_keys()
    fixtures = load_fixtures()
    report = Report()
    for shopper_id, key in keys.items():
        async with MCPClient(
            mcp_url=settings.ctx_mcp_url,
            agent_key=key,
            timeout=settings.ctx_timeout_seconds,
            transport=transport,
        ) as client:
            await check_shopper(client, shopper_id, fixtures, report)
    statuses = {check.status for check in report.checks}
    if "failed" in statuses:
        report.status = "failed"
    elif statuses == {"passed"}:
        report.status = "passed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("export", "seed", "check"))
    parser.add_argument(
        "--output", type=Path, help="Write credential-free JSON output to this file"
    )
    args = parser.parse_args()
    try:
        if args.command == "export":
            output = json.dumps(
                {"data_model": data_model(), "documents": fixture_documents(load_fixtures())},
                indent=2,
            )
            exit_code = 0
        else:
            settings = SmokeSettings()
            if args.command == "seed":
                if not settings.ctx_redis_url.get_secret_value():
                    raise SmokeError("Configure CTX_REDIS_URL for the smoke-test database.")
                with Redis.from_url(
                    settings.ctx_redis_url.get_secret_value(),
                    socket_timeout=20,
                    socket_connect_timeout=20,
                ) as redis:
                    count = seed_documents(redis, fixture_documents(load_fixtures()))
                output, exit_code = json.dumps({"created": count, "verified": 11}), 0
            else:
                report = asyncio.run(run_smoke(settings))
                output = report.model_dump_json(indent=2)
                exit_code = 0 if report.status == "passed" else 1
        if args.output:
            args.output.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
        return exit_code
    except SmokeError as exc:
        print(f"Context Retriever check blocked: {exc}", file=sys.stderr)
    except (ValidationError, RedisError, MCPError, OSError):
        print(
            "Context Retriever check blocked: verify configuration, access and output path.",
            file=sys.stderr,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
