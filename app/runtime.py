"""Local process supervision for independent API and indexing-worker restarts."""

import argparse
import logging
import signal
import subprocess
import sys
import time
from threading import Event
from types import FrameType

logger = logging.getLogger(__name__)


def supervise(
    commands: dict[str, list[str]], stopping: Event, *, restart_delay: float = 2.0
) -> None:
    """Restart exited children; intentional shutdown terminates and reaps them."""
    children: dict[str, subprocess.Popen[bytes]] = {}
    retry_at = dict.fromkeys(commands, 0.0)
    try:
        while not stopping.is_set():
            for name, command in commands.items():
                child = children.get(name)
                if child is not None and child.poll() is not None:
                    logger.warning("%s exited (%s); restarting", name, child.returncode)
                    del children[name]
                    retry_at[name] = time.monotonic() + restart_delay
                if name not in children and time.monotonic() >= retry_at[name]:
                    children[name] = subprocess.Popen(command, start_new_session=True)
                    logger.info("Started %s (PID %s)", name, children[name].pid)
            stopping.wait(0.1)
    finally:
        for child in children.values():
            if child.poll() is None:
                child.terminate()
        for child in children.values():
            try:
                child.wait(timeout=35)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stopping = Event()

    def stop(signum: int, frame: FrameType | None) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    supervise(
        {
            "api": [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.port),
            ],
            "worker": [sys.executable, "-m", "app.worker"],
        },
        stopping,
    )


if __name__ == "__main__":
    main()
