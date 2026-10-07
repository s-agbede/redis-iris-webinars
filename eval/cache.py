"""Evaluate Jev applicability on labelled synthetic camera-shop cases, not total app savings."""

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from statistics import median
from time import perf_counter

from pydantic import BaseModel, Field, JsonValue

from app.shop.jev import JevDecision, JevError, JevVerifier, ReuseRequest
from app.shop.settings import ShopSettings


class CacheCase(BaseModel):
    case_id: str
    expected_reuse: bool
    question: str
    answer: str
    original_question: str = ""
    current_context: dict[str, JsonValue] = Field(default_factory=dict)
    cached_context: dict[str, JsonValue] = Field(default_factory=dict)

    def state(self) -> ReuseRequest:
        return ReuseRequest(
            new_question=self.question,
            cached_question=self.original_question,
            cached_answer=self.answer,
            current_context=self.current_context,
            cached_context=self.cached_context,
        )


class CaseResult(BaseModel):
    case_id: str
    expected_reuse: bool
    reused: bool
    decision: JevDecision | None
    elapsed_ms: float
    error: str | None = None


class CacheReport(BaseModel):
    note: str = (
        "Synthetic applicability checks only. No cache lookup or fallback generation ran. "
        "This report does not measure end-to-end application savings or memory freshness."
    )
    confidence_threshold: float
    valid_reuses: int
    missed_valid_reuses: int
    unsuitable_reuses: int
    errors: int
    median_verification_ms: float
    provider_cost_usd: float | None
    results: list[CaseResult]


def load_cases() -> list[CacheCase]:
    data = json.loads(Path(__file__).with_name("cache_cases.json").read_text())
    return [CacheCase.model_validate(item) for item in data]


def evaluate(
    cases: list[CacheCase],
    verify: Callable[[ReuseRequest], JevDecision],
    *,
    confidence: float,
) -> CacheReport:
    results: list[CaseResult] = []
    for case in cases:
        start = perf_counter()
        decision, error = None, None
        try:
            decision = verify(case.state())
        except JevError as exc:
            error = str(exc)
        reused = (
            decision is not None
            and decision.choice == "accept"
            and decision.confidence >= confidence
        )
        results.append(
            CaseResult(
                case_id=case.case_id,
                expected_reuse=case.expected_reuse,
                reused=reused,
                decision=decision,
                elapsed_ms=round((perf_counter() - start) * 1000, 2),
                error=error,
            )
        )
    costs = [row.decision.cost_usd if row.decision else None for row in results]
    return CacheReport(
        confidence_threshold=confidence,
        valid_reuses=sum(row.reused and row.expected_reuse for row in results),
        missed_valid_reuses=sum(not row.reused and row.expected_reuse for row in results),
        unsuitable_reuses=sum(row.reused and not row.expected_reuse for row in results),
        errors=sum(row.error is not None for row in results),
        median_verification_ms=median(row.elapsed_ms for row in results) if results else 0,
        provider_cost_usd=sum(c for c in costs if c is not None)
        if costs and all(c is not None for c in costs)
        else None,
        results=results,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Validate cases without API calls")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument("--repeat", type=int, default=1, choices=range(1, 11))
    args = parser.parse_args()
    cases = load_cases()
    if args.dry_run:
        print(f"Validated {len(cases)} synthetic cases; no service calls made.")
        return 0
    settings = ShopSettings()
    if settings.cache_missing():
        parser.error("Configure OPENROUTER_API_KEY in .env to run the live Jev evaluation.")
    verifier = JevVerifier(
        settings.openrouter_api_key.get_secret_value(),
        settings.shop_jev_model,
        timeout_seconds=settings.shop_jev_timeout,
    )
    try:
        report = evaluate(
            cases * args.repeat, verifier.verify, confidence=settings.shop_jev_confidence
        )
    finally:
        verifier.close()
    rendered = report.model_dump_json(indent=2)
    if args.output:
        args.output.write_text(rendered + "\n")
    print(rendered)
    return 1 if report.unsuitable_reuses or report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
