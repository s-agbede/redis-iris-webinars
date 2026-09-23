"""Publish the dedicated camera-adviser Skill through the local Playbook UI adapter.

Run from the repository root with ``uv run python -m scripts.setup_shop_playbook``.
Creates only a dedicated shop playbook; never resets other demo content.
Completed stages are checkpointed beside the environment file. An uncertain
creation requires inspection before retrying; it is never automatically repeated.
"""

import argparse
import base64
import io
import os
import sys
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

import httpx
from dotenv import dotenv_values, set_key
from pydantic import BaseModel, ConfigDict

from app.settings import ROOT


class SetupError(RuntimeError):
    """A safe, actionable setup error without upstream data or credentials."""


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    adapter: str
    data_plane: str
    playbook_id: str = ""
    entry_id: str = ""
    version: int = 0
    published: bool = False
    pending: Literal["playbook", "skill", "read key"] | None = None


@contextmanager
def private_replacement(path: Path) -> Iterator[Path]:
    """Replace a file once, after the entire mode-0600 staging file is ready."""
    with NamedTemporaryFile(dir=path.parent, prefix=".shop-playbook-setup-", delete=False) as file:
        staged = Path(file.name)
    try:
        yield staged
        with staged.open("rb") as file:
            os.fsync(file.fileno())
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


def save_checkpoint(path: Path, state: Checkpoint) -> None:
    with private_replacement(path) as staged:
        staged.write_text(state.model_dump_json(), encoding="utf-8")


def save_config(env_file: Path, values: dict[str, str]) -> None:
    with private_replacement(env_file) as staged:
        staged.write_bytes(env_file.read_bytes() if env_file.exists() else b"")
        for name, value in values.items():
            set_key(staged, name, value)


def setup(adapter: str, data_plane: str, env_file: Path) -> None:
    config = dotenv_values(env_file)
    configured = [config.get(f"SHOP_PLAYBOOK_{field}") for field in ("URL", "ID", "API_KEY")]
    if all(configured):
        print("Shop Playbook is already configured; leaving its publication and key unchanged.")
        return
    if any(configured):
        raise SetupError(
            "Shop Playbook configuration is incomplete. Complete the existing URL, ID and API key "
            "settings before retrying; no resources were created."
        )
    checkpoint = env_file.with_name(env_file.name + ".shop-playbook-setup.json")
    state = (
        Checkpoint.model_validate_json(checkpoint.read_text(encoding="utf-8"))
        if checkpoint.exists()
        else Checkpoint(adapter=adapter.rstrip("/"), data_plane=data_plane.rstrip("/"))
    )
    if (state.adapter, state.data_plane) != (adapter.rstrip("/"), data_plane.rstrip("/")):
        raise SetupError("Setup checkpoint belongs to different services. Use its original URLs.")
    if state.pending:
        raise SetupError(
            f"Previous {state.pending} creation has an uncertain outcome. Inspect the service and "
            f"{checkpoint.name} before retrying; automatic replay is blocked."
        )
    package = io.BytesIO()
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "seed/shop/camera-adviser/SKILL.md", "camera-adviser/SKILL.md")
    with httpx.Client(base_url=adapter.rstrip("/"), timeout=30) as client:

        def request(method: str, path: str, body: dict[str, object]) -> dict[str, Any]:
            response = client.request(method, path, json=body)
            response.raise_for_status()
            value: dict[str, Any] = response.json()
            return value

        def creating(stage: Literal["playbook", "skill", "read key"]) -> None:
            state.pending = stage
            save_checkpoint(checkpoint, state)

        if not state.playbook_id:
            creating("playbook")
            playbook = request(
                "POST",
                "/playbooks",
                {
                    "name": "Sam's Camera Shop",
                    "embedding": {"provider": "noop", "model": "playbook-local", "dimensions": 384},
                    "discovery": {"faqMinimumScore": 0, "skillMinimumScore": 0, "maxResults": 5},
                },
            )
            state.playbook_id = str(playbook["playbookId"])
            state.pending = None
            save_checkpoint(checkpoint, state)
            print(f"Created dedicated shop playbook {state.playbook_id}.")
        if not state.entry_id:
            creating("skill")
            created = request(
                "POST",
                f"/playbooks/{state.playbook_id}/skills",
                {
                    "entryKey": "camera-adviser",
                    "packageBase64": base64.b64encode(package.getvalue()).decode(),
                    "content": {
                        "intents": ["recommend a camera", "compare cameras", "choose a camera kit"]
                    },
                },
            )
            state.entry_id = str(created["entry"]["entryId"])
            state.version = int(created["version"]["version"])
            state.pending = None
            save_checkpoint(checkpoint, state)
        if not state.published:
            # Publishing the same exact version is safe to repeat after a lost response.
            request(
                "PUT",
                f"/playbooks/{state.playbook_id}/entries/skill/{state.entry_id}/publication",
                {"version": state.version},
            )
            state.published = True
            save_checkpoint(checkpoint, state)
        creating("read key")
        key = request(
            "POST",
            f"/playbooks/{state.playbook_id}/agent-keys",
            {
                "name": "sams-camera-shop-reader",
                "actions": ["read"],
            },
        )
        save_config(
            env_file,
            {
                "SHOP_PLAYBOOK_URL": data_plane,
                "SHOP_PLAYBOOK_ID": state.playbook_id,
                "SHOP_PLAYBOOK_API_KEY": str(key["token"]),
            },
        )
        checkpoint.unlink()
        print(f"Published camera-adviser v{state.version}; saved its read key to {env_file.name}.")
        print("This local playbook uses noop embeddings. The demonstration uses a pinned Skill.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", default="http://127.0.0.1:18080/demo/api")
    parser.add_argument("--data-plane", default="http://127.0.0.1:9301")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    try:
        setup(args.adapter, args.data_plane, args.env_file)
    except SetupError as exc:
        print(f"Playbook setup failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as exc:
        print(
            f"Playbook setup failed: HTTP {exc.response.status_code}. Check the local adapter.",
            file=sys.stderr,
        )
        sys.exit(1)
    except (httpx.RequestError, KeyError, ValueError, OSError) as exc:
        print(
            f"Playbook setup failed ({type(exc).__name__}); check service readiness and contract.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
