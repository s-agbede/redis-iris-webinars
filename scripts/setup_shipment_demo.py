"""Publish, migrate and replay only the camera shop's fictional shipment demo."""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import cast

import httpx
from context_surfaces.client import ContextSurfacesClient
from context_surfaces.exceptions import ContextSurfacesError
from context_surfaces.models import UpdateContextSurfaceRequest
from pydantic import JsonValue, SecretStr, ValidationError
from redis import Redis
from redis.exceptions import RedisError, WatchError

from scripts.check_context_retriever import SmokeError, SmokeSettings, same_json
from seed.shop_context import PREFIX, data_model, fixture_documents, load_fixtures


class SetupSettings(SmokeSettings):
    ctx_admin_key: SecretStr = SecretStr("")
    ctx_surface_id: str = ""


def migrate_documents(
    client: Redis,
    previous: dict[str, dict[str, JsonValue]],
    desired: dict[str, dict[str, JsonValue]],
) -> int:
    """Atomically create/upgrade fixtures, rejecting all unrecognized existing data."""
    with client.pipeline() as pipe:
        try:
            pipe.watch(*desired)  # type: ignore[no-untyped-call]
            changed: list[str] = []
            for key, body in desired.items():
                existing = cast(dict[str, JsonValue] | None, pipe.json().get(key))
                if same_json(existing, body):
                    continue
                if (existing is None and not pipe.exists(key)) or (
                    key in previous and same_json(existing, previous[key])
                ):
                    changed.append(key)
                else:
                    raise SmokeError(f"Fixture {key} contains different data; nothing written.")
            pipe.multi()
            for key in changed:
                pipe.execute_command(  # type: ignore[no-untyped-call]
                    "JSON.SET", key, "$", json.dumps(desired[key])
                )
            results = pipe.execute()
            if len(results) != len(changed) or not all(results):
                raise SmokeError("A fixture write was not acknowledged; inspect the records.")
            return len(changed)
        except WatchError:
            raise SmokeError("Fixture data changed during migration; inspect and retry.") from None


def shipment_states() -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    """Two dated fictional snapshots for a repeatable live-read demonstration."""
    record = next(s for s in load_fixtures().shipments if s.shipment_id == "SHIP-1002")
    delayed = record.model_dump(mode="json")
    delivered = delayed | {
        "status": "delivered",
        "latest_event": "Delivered to the recipient",
        "updated_at": "2026-09-30T14:00:00Z",
    }
    return delayed, delivered


async def publish(
    settings: SetupSettings, backup: Path, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, JsonValue]:
    """Update only this demo surface's model, retaining its credentials and data source."""
    if not settings.ctx_admin_key.get_secret_value() or not settings.ctx_surface_id:
        raise SmokeError("Configure CTX_ADMIN_KEY and CTX_SURFACE_ID to publish the demo model.")
    async with ContextSurfacesClient(transport=transport) as client:
        surface = await client.get_context_surface(
            settings.ctx_surface_id, admin_key=settings.ctx_admin_key.get_secret_value()
        )
        entities = (surface.data_model or {}).get("entities", [])
        if surface.name != "camera-shop-context-smoke" or not entities:
            raise SmokeError("Configured surface is not the existing camera shop demo.")
        if {e["name"] for e in entities} not in (
            {"Shopper", "Purchase", "Product"},
            {"Shopper", "Purchase", "Product", "Shipment"},
        ):
            raise SmokeError("The demo surface contains an unexpected entity; nothing published.")
        if any(not e.get("redis_key_template", "").startswith(PREFIX + ":") for e in entities):
            raise SmokeError("The surface uses a different data prefix; nothing published.")
        backup.write_text(json.dumps(surface.data_model, indent=2) + "\n", encoding="utf-8")
        updated = await client.update_context_surface(
            settings.ctx_surface_id,
            UpdateContextSurfaceRequest(
                data_model=data_model(),
                name=None,
                description=None,
                metadata=None,
                identity_provider=None,
            ),
            admin_key=settings.ctx_admin_key.get_secret_value(),
        )
    return {"name": updated.name, "status": updated.status, "tools": len(updated.tools)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("migrate", "publish", "delayed", "delivered"))
    parser.add_argument(
        "--backup", type=Path, default=Path("/tmp/camera-context-model-before.json")
    )
    args = parser.parse_args()
    # SDK error logs may include upstream response text; the CLI emits safe errors below.
    logging.getLogger("context_surfaces").setLevel(logging.CRITICAL)
    try:
        settings = SetupSettings()
        if args.command == "publish":
            result = asyncio.run(publish(settings, args.backup))
        else:
            if not settings.ctx_redis_url.get_secret_value():
                raise SmokeError("Configure CTX_REDIS_URL for the demo database.")
            with Redis.from_url(
                settings.ctx_redis_url.get_secret_value(),
                socket_timeout=20,
                socket_connect_timeout=20,
            ) as client:
                if args.command == "migrate":
                    from seed.shop_context import legacy_fixture_documents

                    changed = migrate_documents(
                        client, legacy_fixture_documents(), fixture_documents(load_fixtures())
                    )
                else:
                    delayed, delivered = shipment_states()
                    key = f"{PREFIX}:shipment:SHIP-1002"
                    previous, desired = (
                        (delayed, delivered)
                        if args.command == "delivered"
                        else (delivered, delayed)
                    )
                    changed = migrate_documents(client, {key: previous}, {key: desired})
                result = {"command": args.command, "changed": changed}
        print(json.dumps(result))
        return 0
    except SmokeError as exc:
        print(str(exc), file=sys.stderr)
    except (ContextSurfacesError, httpx.HTTPError, RedisError, ValidationError, OSError):
        print(
            "Demo setup failed; check configuration, access and service readiness.", file=sys.stderr
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
