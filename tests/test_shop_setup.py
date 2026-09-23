from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from dotenv import dotenv_values, set_key

from scripts import setup_shop_playbook as shop_setup

ADAPTER = "http://adapter.example.test"
DATA_PLANE = "http://playbook.example.test"


class Adapter:
    def __init__(self, fail_path: str | None = None) -> None:
        self.calls: list[str] = []
        self.fail_path = fail_path

    def respond(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(path)
        if path == self.fail_path:
            self.fail_path = None
            raise httpx.ReadTimeout("Fixture connection failed.")
        if path == "/playbooks":
            return httpx.Response(201, json={"playbookId": "shop-only"})
        if path == "/playbooks/shop-only/skills":
            return httpx.Response(
                201, json={"entry": {"entryId": "adviser"}, "version": {"version": 3}}
            )
        if path == "/playbooks/shop-only/entries/skill/adviser/publication":
            return httpx.Response(200, json={})
        if path == "/playbooks/shop-only/agent-keys":
            return httpx.Response(201, json={"token": "fixture-read-secret"})
        pytest.fail(f"Unexpected setup request: {path}")


def connect(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    client_type = httpx.Client

    def client(**kwargs: Any) -> httpx.Client:
        return client_type(**kwargs, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("scripts.setup_shop_playbook.httpx.Client", client)


def test_retry_resumes_the_created_resource_after_publication_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Adapter("/playbooks/shop-only/entries/skill/adviser/publication")
    connect(monkeypatch, backend.respond)
    env_file = tmp_path / ".env"

    with pytest.raises(httpx.ReadTimeout):
        shop_setup.setup(ADAPTER, DATA_PLANE, env_file)
    shop_setup.setup(ADAPTER, DATA_PLANE, env_file)

    assert backend.calls.count("/playbooks") == 1
    assert backend.calls.count("/playbooks/shop-only/skills") == 1
    assert backend.calls.count("/playbooks/shop-only/entries/skill/adviser/publication") == 2
    assert dotenv_values(env_file)["SHOP_PLAYBOOK_ID"] == "shop-only"


@pytest.mark.parametrize(
    "stage", ["/playbooks", "/playbooks/shop-only/skills", "/playbooks/shop-only/agent-keys"]
)
def test_ambiguous_creation_is_not_replayed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    backend = Adapter(stage)
    connect(monkeypatch, backend.respond)
    env_file = tmp_path / ".env"

    with pytest.raises(httpx.ReadTimeout):
        shop_setup.setup(ADAPTER, DATA_PLANE, env_file)
    checkpoint = env_file.with_name(env_file.name + ".shop-playbook-setup.json")
    assert checkpoint.stat().st_mode & 0o777 == 0o600
    prior_calls = list(backend.calls)
    with pytest.raises(RuntimeError, match="uncertain"):
        shop_setup.setup(ADAPTER, DATA_PLANE, env_file)

    assert backend.calls == prior_calls


def test_incomplete_existing_config_fails_without_creating_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Adapter()
    connect(monkeypatch, backend.respond)
    env_file = tmp_path / ".env"
    original = "SHOP_PLAYBOOK_ID=existing\nOTHER_SECRET=preserve\n"
    env_file.write_text(original)

    with pytest.raises(RuntimeError, match="incomplete"):
        shop_setup.setup(ADAPTER, DATA_PLANE, env_file)

    assert backend.calls == []
    assert env_file.read_text() == original


def test_configuration_write_failure_preserves_the_entire_original_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Adapter()
    connect(monkeypatch, backend.respond)
    env_file = tmp_path / ".env"
    original = "# Keep this comment\nOTHER_SECRET='preserve-me'\n"
    env_file.write_text(original)

    def fail_second_setting(path: Path, name: str, value: str) -> tuple[bool | None, str, str]:
        if name == "SHOP_PLAYBOOK_ID":
            raise OSError("Fixture disk write failed.")
        return set_key(path, name, value)

    monkeypatch.setattr(shop_setup, "set_key", fail_second_setting)

    with pytest.raises(OSError):
        shop_setup.setup(ADAPTER, DATA_PLANE, env_file)

    assert env_file.read_text() == original
    checkpoint = env_file.with_name(env_file.name + ".shop-playbook-setup.json")
    assert "fixture-read-secret" not in checkpoint.read_text()
    assert not list(tmp_path.glob(".shop-playbook-setup-*"))
    prior_calls = list(backend.calls)
    with pytest.raises(RuntimeError, match="uncertain"):
        shop_setup.setup(ADAPTER, DATA_PLANE, env_file)
    assert backend.calls == prior_calls


def test_success_preserves_other_env_content_and_existing_complete_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    backend = Adapter()
    connect(monkeypatch, backend.respond)
    env_file = tmp_path / ".env"
    original = "# Keep this comment\nOTHER_SECRET='preserve-me'\n"
    env_file.write_text(original)

    shop_setup.setup(ADAPTER, DATA_PLANE, env_file)
    configured = env_file.read_bytes()
    prior_calls = list(backend.calls)
    shop_setup.setup(ADAPTER, DATA_PLANE, env_file)

    assert env_file.read_text().startswith(original)
    assert dotenv_values(env_file)["SHOP_PLAYBOOK_API_KEY"] == "fixture-read-secret"
    assert env_file.stat().st_mode & 0o777 == 0o600
    assert env_file.read_bytes() == configured
    assert backend.calls == prior_calls
    assert not list(tmp_path.glob("*.shop-playbook-setup.json"))
    output = capsys.readouterr()
    assert "fixture-read-secret" not in output.out + output.err
    assert "preserve-me" not in output.out + output.err


def test_resume_rejects_a_different_service_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Adapter("/playbooks/shop-only/entries/skill/adviser/publication")
    connect(monkeypatch, backend.respond)
    env_file = tmp_path / ".env"

    with pytest.raises(httpx.ReadTimeout):
        shop_setup.setup(ADAPTER, DATA_PLANE, env_file)
    prior_calls = list(backend.calls)
    with pytest.raises(RuntimeError, match="different"):
        shop_setup.setup("http://different.example.test", DATA_PLANE, env_file)

    assert backend.calls == prior_calls
