"""Run the labelled cases against the real index and print the scoreboard.

    uv run python -m eval.run --config all
    make eval CONFIG=hybrid

Two jobs, and it matters that they are separate:

  1. The scoreboard. Three modes, the same eleven cases, a rising pass count.
     That is the episode's argument as a number rather than a claim, and it can
     be run live.
  2. The regression guard. Every case records what each mode actually did the
     last time someone looked. Exit code is nonzero when reality and the record
     disagree — in either direction. See `EvalCase.expect`.

Exit codes: 0 all modes match the record, 1 they do not, 2 the harness could
not run at all (no index, no key).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from app.models import SearchMode
from app.search import Searcher, build_searcher
from eval.models import CaseOutcome, EvalCase, ModeReport, judge

CASES = Path("eval/cases.yaml")
TOP_N_VERBOSE = 5

PASS_MARK, FAIL_MARK = "✓", "✗"


def load_cases(path: Path = CASES) -> list[EvalCase]:
    raw = yaml.safe_load(path.read_text())
    cases = [EvalCase.model_validate(entry) for entry in raw]

    # case_id is the report's row key, so a duplicate would silently drop a row
    # rather than fail — worth one line to catch.
    duplicates = {c.case_id for c in cases if sum(1 for o in cases if o.case_id == c.case_id) > 1}
    if duplicates:
        raise ValueError(f"duplicate case_id in {path}: {sorted(duplicates)}")
    return cases


def run_mode(
    searcher: Searcher, cases: list[EvalCase], mode: SearchMode, *, verbose: bool
) -> ModeReport:
    """Every case, one mode. Results are printed by the caller, not here."""
    outcomes: list[CaseOutcome] = []
    for case in cases:
        result = searcher.search(query=case.query, mode=mode, filters=case.filters)
        outcome = judge(case, mode, [hit.product_id for hit in result.hits])
        outcomes.append(outcome)

        if verbose:
            print(f"\n  [{mode}] {case.case_id}: {case.query!r}")
            for rank, hit in enumerate(result.hits[:TOP_N_VERBOSE], start=1):
                marker = "<-- answer" if hit.product_id in case.answers else ""
                if hit.product_id in case.forbidden:
                    marker = "<-- SHOULD BE FILTERED OUT"
                print(
                    f"    {rank}. {hit.product_id}  {hit.name[:52]:<52} "
                    f"{hit.price:>7.2f}  {hit.score:.4f} {marker}"
                )

    return ModeReport(mode=mode, outcomes=outcomes)


def _cell(outcome: CaseOutcome) -> str:
    """One matrix cell: verdict, the rank it achieved, and a regression flag."""
    rank = f"#{outcome.answer_rank}" if outcome.answer_rank else "--"
    mark = PASS_MARK if outcome.passed else FAIL_MARK
    return f"{mark} {rank}{'!' if outcome.regressed else ''}"


def print_scoreboard(reports: list[ModeReport], cases: list[EvalCase]) -> None:
    """The matrix that goes on screen. Cases down, modes across."""
    label_width = max(len(c.case_id) for c in cases) + 2
    header = "case".ljust(label_width) + "".join(str(r.mode).upper().ljust(12) for r in reports)
    print(f"\n{header}")
    print("-" * len(header))

    by_case = {(o.case_id, o.mode): o for report in reports for o in report.outcomes}
    for case in cases:
        row = case.case_id.ljust(label_width)
        row += "".join(_cell(by_case[(case.case_id, r.mode)]).ljust(12) for r in reports)
        print(row)

    print("-" * len(header))
    print("passed".ljust(label_width) + "".join(f"{r.passed}/{r.total}".ljust(12) for r in reports))
    print("MRR".ljust(label_width) + "".join(f"{r.mrr:.2f}".ljust(12) for r in reports))


def print_failures(reports: list[ModeReport], cases: list[EvalCase]) -> None:
    """Why each failing case failed. 'FAIL' alone is not actionable."""
    by_id = {c.case_id: c for c in cases}
    for report in reports:
        failures = [o for o in report.outcomes if not o.passed]
        if not failures:
            continue
        print(f"\n{str(report.mode).upper()} — {len(failures)} of {report.total} failing")
        for outcome in failures:
            print(f"  {outcome.case_id}")
            print(f"    query   {by_id[outcome.case_id].query!r}")
            print(f"    reason  {outcome.reason}")


def print_regressions(reports: list[ModeReport]) -> bool:
    """Report any disagreement with the recorded baseline. Returns True if any."""
    regressions = [o for report in reports for o in report.regressions]
    if not regressions:
        return False

    print(f"\n{'=' * 60}")
    print(f"{len(regressions)} case(s) disagree with the baseline in eval/cases.yaml:")
    for outcome in regressions:
        was = "pass" if outcome.expected else "fail"
        now = "pass" if outcome.passed else "fail"
        print(f"  [{outcome.mode}] {outcome.case_id}: recorded {was}, now {now}")
        if outcome.reason:
            print(f"      {outcome.reason}")
    print(
        "\nIf the change was intended, update `expect` in eval/cases.yaml and say\n"
        "why in the commit. If it was not, this is the demo breaking before the call."
    )
    return True


def record_baseline(path: Path, reports: list[ModeReport]) -> int:
    """Rewrite the `expect:` blocks in the case file from what actually happened.

    Curating cases means editing a query, running it, and seeing where it lands.
    Hand-copying verdicts back into YAML during that loop is busywork and an
    easy place to introduce a wrong baseline, which is worse than no baseline.

    Edited line-by-line rather than by round-tripping through a YAML parser,
    because PyYAML would strip every comment in the file and the comments are
    doing real work. Only lines matching `    <mode>: pass|fail` under an
    `expect:` key are touched.

    Returns the number of verdicts changed.
    """
    observed = {
        (outcome.case_id, str(outcome.mode)): outcome.passed
        for report in reports
        for outcome in report.outcomes
    }

    lines = path.read_text().splitlines(keepends=True)
    case_id: str | None = None
    in_expect = False
    changed = 0

    for i, line in enumerate(lines):
        if match := re.match(r"^- case_id: (\S+)", line):
            case_id, in_expect = match.group(1), False
            continue
        if re.match(r"^  expect:\s*$", line):
            in_expect = True
            continue
        if in_expect and (match := re.match(r"^(\s+)(\w+): (pass|fail)\s*$", line)):
            mode, was = match.group(2), match.group(3)
            now = observed.get((case_id or "", mode))
            if now is None:  # a mode this run did not cover — leave it alone
                continue
            word = "pass" if now else "fail"
            if word != was:
                lines[i] = f"{match.group(1)}{mode}: {word}\n"
                changed += 1
        elif in_expect and not line.startswith("    "):
            in_expect = False

    path.write_text("".join(lines))
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        default="all",
        choices=[*(str(m) for m in SearchMode), "all"],
        help="which retrieval mode to evaluate (default: all)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help=f"show the top {TOP_N_VERBOSE} hits per case"
    )
    parser.add_argument("--cases", type=Path, default=CASES, help="path to the case file")
    parser.add_argument(
        "--record",
        action="store_true",
        help="rewrite `expect:` in the case file from this run, then exit 0. "
        "Use while curating cases; never use it to silence a red build you "
        "have not explained.",
    )
    args = parser.parse_args()

    cases = load_cases(args.cases)
    modes = list(SearchMode) if args.config == "all" else [SearchMode(args.config)]

    try:
        searcher = build_searcher()
    except Exception as error:  # noqa: BLE001 — surface the cause, do not mask it
        print(f"cannot reach the products index: {error}\n\nTry: make seed", file=sys.stderr)
        return 2

    print(f"{len(cases)} cases x {len(modes)} mode(s) against '{searcher.settings.products_index}'")

    reports = [run_mode(searcher, cases, mode, verbose=args.verbose) for mode in modes]

    print_scoreboard(reports, cases)
    print_failures(reports, cases)

    if args.record:
        changed = record_baseline(args.cases, reports)
        covered = ", ".join(str(r.mode) for r in reports)
        print(f"\nrecorded {changed} changed verdict(s) in {args.cases} ({covered})")
        return 0

    return 1 if print_regressions(reports) else 0


if __name__ == "__main__":
    sys.exit(main())
