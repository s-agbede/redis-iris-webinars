"""Separate-process, closed-loop HTTP client for the camera performance lab."""

import argparse
import asyncio
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx

from app.traffic import TrafficMetrics, TrafficRequest, TrafficRun, local_target

WORKLOAD = (
    {"query": "Sony Alpha a7", "brands": [], "colors": [], "num_results": 6},
    {"query": "lightweight camera for travel", "brands": [], "colors": [], "num_results": 6},
    {"query": "Canon EOS", "brands": ["Canon"], "colors": [], "num_results": 6},
    {"query": "wildlife photography", "brands": ["Nikon"], "colors": [], "num_results": 6},
)


@dataclass(frozen=True)
class Sample:
    milliseconds: float
    outcome: Literal["success", "error", "timeout"]


def percentile(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sorted(values)[math.ceil(len(values) * 0.95) - 1], 3)


def summarize(samples: list[Sample], elapsed: float) -> TrafficMetrics:
    return TrafficMetrics(
        attempts=len(samples),
        successful=sum(s.outcome == "success" for s in samples),
        errors=sum(s.outcome == "error" for s in samples),
        timeouts=sum(s.outcome == "timeout" for s in samples),
        p95_success_ms=percentile([s.milliseconds for s in samples if s.outcome == "success"]),
        p95_all_ms=percentile([s.milliseconds for s in samples]),
        completed_per_sec=round(len(samples) / elapsed, 3) if elapsed > 0 else 0,
        elapsed_seconds=round(elapsed, 3),
    )


async def measure(target: str, config: TrafficRequest) -> TrafficMetrics:
    samples: list[Sample] = []
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(3),
        trust_env=False,
        limits=httpx.Limits(max_connections=config.concurrency),
    ) as client:
        started = time.monotonic()
        deadline = started + config.duration

        async def worker(offset: int) -> None:
            index = offset
            while time.monotonic() < deadline:
                before = time.monotonic()
                outcome: Literal["success", "error", "timeout"] = "error"
                try:
                    async with asyncio.timeout(3):
                        response = await client.post(
                            f"{target}/api/search",
                            json={
                                **WORKLOAD[index % len(WORKLOAD)],
                                "cache_embedding": config.cache_embedding,
                            },
                        )
                        response.raise_for_status()
                        data = response.json()
                        results = data.get("results") if isinstance(data, dict) else None
                        if (
                            isinstance(results, list)
                            and len(results) == 1
                            and isinstance(results[0], dict)
                            and not results[0].get("error")
                            and isinstance(results[0].get("hits"), list)
                        ):
                            outcome = "success"
                except (httpx.TimeoutException, TimeoutError):
                    outcome = "timeout"
                except (httpx.HTTPError, ValueError):
                    outcome = "error"
                samples.append(Sample((time.monotonic() - before) * 1000, outcome))
                index += 1

        await asyncio.gather(*(worker(i) for i in range(config.concurrency)))
        return summarize(samples, time.monotonic() - started)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True)
    parser.add_argument("--concurrency", type=int, required=True)
    parser.add_argument("--duration", type=int, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--cache-embedding", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = TrafficRequest.model_validate(
        {
            "concurrency": args.concurrency,
            "duration": args.duration,
            "cache_embedding": args.cache_embedding,
        }
    )
    metrics = asyncio.run(measure(local_target(args.target), config))
    result = TrafficRun(
        run_id=args.run_id, state="completed", **config.model_dump(), **metrics.model_dump()
    )
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(result.model_dump_json())
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
