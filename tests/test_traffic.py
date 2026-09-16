"""Boundaries and accounting for the local traffic lab."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.traffic import TrafficController, TrafficRequest, local_target
from scripts.search_load import Sample, summarize


def test_metrics_keep_timeouts_and_failures_in_all_latency() -> None:
    result = summarize([Sample(10, "success"), Sample(30, "error"), Sample(3000, "timeout")], 5)
    assert result.attempts == 3
    assert result.successful == 1
    assert result.errors == 1
    assert result.timeouts == 1
    assert result.p95_success_ms == 10
    assert result.p95_all_ms == 3000
    assert result.completed_per_sec == 0.6


def test_empty_metrics_have_no_fake_latency() -> None:
    result = summarize([], 0)
    assert result.p95_success_ms is None
    assert result.p95_all_ms is None
    assert result.completed_per_sec == 0


@pytest.mark.parametrize("concurrency,duration", [(2, 5), (20, 31), (1, 4)])
def test_run_bounds(concurrency: int, duration: int) -> None:
    with pytest.raises(ValidationError):
        TrafficRequest(concurrency=concurrency, duration=duration)


def test_local_target_rejects_external_and_credential_urls() -> None:
    assert local_target("http://localhost:8123/") == "http://127.0.0.1:8123"
    for url in [
        "http://example.com:8000",
        "http://127.0.0.1@evil.test",
        "https://localhost:8000",
        "http://user@localhost:8000",
    ]:
        with pytest.raises(ValueError):
            local_target(url)


def test_controller_stops_only_its_child_and_rejects_overlap(tmp_path: Path) -> None:
    # A sleeping child exercises real process cleanup without sending any HTTP traffic.
    controller = TrafficController(tmp_path)
    controller.command = lambda *_: [sys.executable, "-c", "import time; time.sleep(60)"]
    first = controller.start(TrafficRequest(concurrency=1, duration=5), "http://localhost:8123")
    assert first.state == "running"
    with pytest.raises(RuntimeError, match="already running"):
        controller.start(TrafficRequest(), "http://localhost:8123")
    stopped = controller.stop()
    assert stopped is not None and stopped.state == "stopped"
    assert controller.process is None


def test_controller_reports_child_failure(tmp_path: Path) -> None:
    controller = TrafficController(tmp_path)
    controller.command = lambda *_: [sys.executable, "-c", "raise SystemExit(9)"]
    controller.start(TrafficRequest(), "http://localhost:8123")
    assert controller.process is not None
    controller.process.wait(timeout=3)
    result = controller.status()
    assert result is not None and result.state == "failed"
    assert result.error and "9" in result.error
