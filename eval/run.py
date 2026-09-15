"""Inspect real rankings and judgement coverage. This is an exploratory report, not a benchmark."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.models import CompareRequest
from app.search import build_searcher
from app.settings import ROOT
from eval.models import ReviewedCase, assess


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all-source", action="store_true", help="Run all 183 selected source queries"
    )
    parser.add_argument("--check", action="store_true", help="Fail configured target-rank checks")
    parser.add_argument("--output", type=Path, default=ROOT / "eval/latest.json")
    args = parser.parse_args()
    reviewed = [
        ReviewedCase.model_validate(value)
        for value in yaml.safe_load((ROOT / "eval/cases.yaml").read_text())
    ]
    by_query = {case.query: case for case in reviewed}
    searcher = build_searcher()
    cases = reviewed
    if args.all_source:
        cases = [
            by_query.get(
                query, ReviewedCase(case_id=str(qid), query=query, notes="Original ESCI query")
            )
            for qid, query in sorted(
                {j.query_id: j.query for j in searcher.catalog.judgements}.items()
            )
        ]
    reports = []
    errors = 0
    failures: list[str] = []
    try:
        for case in cases:
            unknown = set(case.judgements) - searcher.catalog.products.keys()
            if unknown:
                raise ValueError(f"{case.case_id}: unknown catalogue IDs: {sorted(unknown)}")
            if case.required_modes and (
                case.required_top_k is None or "relevant" not in case.judgements.values()
            ):
                raise ValueError(f"{case.case_id}: required modes need a threshold and target")
            result = searcher.compare(
                CompareRequest(query=case.query, brands=case.brands, include_basic=True)
            )
            assessments = {row.mode: assess(row.hits, case).model_dump() for row in result.results}
            reports.append(
                {
                    "case": case.model_dump(),
                    "comparison": result.model_dump(mode="json"),
                    "assessment": assessments,
                }
            )
            errors += sum(row.error is not None for row in result.results)
            print(case.query, flush=True)
            for row in result.results:
                if row.mode in case.required_modes and (
                    row.error or assessments[row.mode]["expectation_passed"] is not True
                ):
                    failures.append(
                        f"{case.case_id}/{row.mode}: target missing from top {case.required_top_k}"
                    )
                print(
                    f"  {row.mode:6} top={row.hits[0].product_id if row.hits else 'none'} "
                    f"target_rank={assessments[row.mode]['first_reviewed_relevant_rank']} "
                    f"latency={row.query_ms:.1f}ms "
                    f"review={assessments[row.mode]['reviewed_top_label']} "
                    f"judged={assessments[row.mode]['source_judged']}/{len(row.hits)} "
                    f"error={row.error or 'none'}",
                    flush=True,
                )
    finally:
        searcher.index.disconnect()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "recorded_at": datetime.now(UTC).isoformat(),
                "execution_errors": errors,
                "quality_failures": failures,
                "scope": (
                    "Exploratory. Source labels are sparse and imperfect; "
                    "assistant-reviewed catalogue judgements "
                    "are a limited pool. Unjudged is not irrelevant. "
                    "No held-out quality or performance claim."
                ),
                "reports": reports,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Report: {args.output}")
    for failure in failures:
        print(f"FAIL: {failure}")
    return 1 if errors or (args.check and failures) else 0


if __name__ == "__main__":
    raise SystemExit(main())
