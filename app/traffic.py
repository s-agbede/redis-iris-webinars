"""Bounded local HTTP load runs, isolated from the API process."""

import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parents[1]


class TrafficRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    concurrency: Literal[1, 5, 10, 20] = 1
    duration: int = Field(default=10, ge=5, le=30)
    cache_embedding: bool = False


class TrafficMetrics(BaseModel):
    attempts: int = 0
    successful: int = 0
    errors: int = 0
    timeouts: int = 0
    p95_success_ms: float | None = None
    p95_all_ms: float | None = None
    completed_per_sec: float = 0
    elapsed_seconds: float = 0


class TrafficRun(TrafficMetrics):
    run_id: str
    state: Literal["running", "completed", "stopped", "failed"]
    concurrency: int
    duration: int
    cache_embedding: bool = False
    workload: str = "camera-mix-v1: 4 rotating model/intent queries; 2 brand-filtered; top 6"
    measurement: str = "Closed-loop HTTP; separate client process on the same machine; no warm-up"
    error: str | None = None


def local_target(url: str) -> str:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("Traffic runs require a local HTTP server URL.")
    return f"http://127.0.0.1:{parsed.port or 80}"


class TrafficController:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or Path(tempfile.mkdtemp(prefix="camera-traffic-"))
        self.lock = threading.Lock()
        self.process: subprocess.Popen[bytes] | None = None
        self.current: TrafficRun | None = None
        self.started = 0.0

    def command(self, run: TrafficRun, target: str, output: Path) -> list[str]:
        return [
            sys.executable,
            "-m",
            "scripts.search_load",
            "--target",
            target,
            "--concurrency",
            str(run.concurrency),
            "--duration",
            str(run.duration),
            "--run-id",
            run.run_id,
            *(["--cache-embedding"] if run.cache_embedding else []),
            "--output",
            str(output),
        ]

    def _status(self) -> TrafficRun | None:
        if self.current is None or self.process is None:
            return self.current
        code = self.process.poll()
        if code is None:
            self.current.elapsed_seconds = round(time.monotonic() - self.started, 3)
            return self.current
        output = self.directory / f"{self.current.run_id}.json"
        try:
            if code != 0:
                raise ValueError(f"Traffic runner exited with code {code}.")
            completed = TrafficRun.model_validate_json(output.read_text())
            if completed.run_id != self.current.run_id or completed.state != "completed":
                raise ValueError("Traffic runner returned an invalid result.")
            self.current = completed
        except (OSError, ValueError) as exc:
            self.current.state = "failed"
            self.current.error = str(exc)
        finally:
            output.unlink(missing_ok=True)
            self.process = None
        return self.current

    def status(self) -> TrafficRun | None:
        with self.lock:
            return self._status()

    def start(self, config: TrafficRequest, target: str) -> TrafficRun:
        target = local_target(target)
        with self.lock:
            self._status()
            if self.process is not None:
                raise RuntimeError("A traffic run is already running.")
            run = TrafficRun(run_id=uuid4().hex, state="running", **config.model_dump())
            output = self.directory / f"{run.run_id}.json"
            self.process = subprocess.Popen(
                self.command(run, target, output),
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.current = run
            self.started = time.monotonic()
            return run

    def stop(self) -> TrafficRun | None:
        with self.lock:
            self._status()
            if self.process is not None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
                self.process = None
                if self.current is not None:
                    self.current.state = "stopped"
                    self.current.elapsed_seconds = round(time.monotonic() - self.started, 3)
                    self.current.error = "Stopped early; partial measurements are discarded."
                    (self.directory / f"{self.current.run_id}.json").unlink(missing_ok=True)
            return self.current


controller = TrafficController()
router = APIRouter(prefix="/api/lab/traffic", tags=["performance"])


def stop_traffic() -> None:
    controller.stop()


@router.get("")
def traffic_status() -> TrafficRun | None:
    return controller.status()


@router.post("")
def start_traffic(body: TrafficRequest, request: Request) -> TrafficRun:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Traffic runs are available only from this machine.")
    try:
        target = os.environ.get("CAMERA_TRAFFIC_TARGET", str(request.base_url))
        return controller.start(body, target)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, f"Cannot start traffic runner: {exc}") from exc


@router.post("/stop")
def stop_traffic_route(request: Request) -> TrafficRun | None:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Traffic runs are available only from this machine.")
    return controller.stop()
