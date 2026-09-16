"""Exercise restart and shutdown with real child processes."""

import sys
import time
from threading import Event, Thread

from app.runtime import supervise


def test_exited_process_restarts_and_shutdown_stops_children(tmp_path):
    launches = tmp_path / "launches"
    program = (
        "import os,pathlib,time; "
        f"p=pathlib.Path({str(launches)!r}); "
        "n=int(p.read_text()) if p.exists() else 0; p.write_text(str(n+1)); "
        "time.sleep(0.05); os._exit(1)"
    )
    stop = Event()
    thread = Thread(
        target=supervise,
        args=({"worker": [sys.executable, "-c", program]}, stop),
        kwargs={"restart_delay": 0.05},
    )
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if launches.exists() and launches.read_text() == "2":
                break
            time.sleep(0.01)
        assert int(launches.read_text()) >= 2
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive()


def test_killed_worker_restarts_without_restarting_api(tmp_path):
    import os
    import signal

    def command(name):
        path = tmp_path / name
        return [
            sys.executable,
            "-c",
            (
                "import os,pathlib,time; "
                f"pathlib.Path({str(path)!r}).write_text(str(os.getpid())); time.sleep(60)"
            ),
        ]

    def read_pid(name, previous=None):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            path = tmp_path / name
            value = path.read_text() if path.exists() else ""
            if value and int(value) != previous:
                return int(value)
            time.sleep(0.01)
        raise AssertionError(f"{name} did not start")

    stop = Event()
    thread = Thread(
        target=supervise,
        args=({"api": command("api"), "worker": command("worker")}, stop),
        kwargs={"restart_delay": 0.05},
    )
    thread.start()
    try:
        api_pid, worker_pid = read_pid("api"), read_pid("worker")
        os.kill(worker_pid, signal.SIGKILL)
        replacement = read_pid("worker", worker_pid)
        assert read_pid("api") == api_pid
    finally:
        stop.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    for pid in (api_pid, replacement):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            continue
        raise AssertionError(f"Child {pid} survived shutdown")
