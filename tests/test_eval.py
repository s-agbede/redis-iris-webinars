"""Tests for the judging rule.

These need no Redis, no OpenAI key and no seeded index — `judge` takes a
ranking and returns a verdict, so the part of the eval that decides what
"correct" means is testable in milliseconds. The runner around it is wiring.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import SearchMode
from eval.models import CaseOutcome, EvalCase, ModeReport, judge


def make_case(**overrides: object) -> EvalCase:
    """An otherwise-valid case, so each test states only what it cares about."""
    defaults: dict[str, object] = {
        "case_id": "example",
        "query": "waterproof jacket",
        "why": "test fixture",
        "answers": ["H00001"],
        "expect": {"text": "fail", "vector": "fail", "hybrid": "pass"},
    }
    return EvalCase.model_validate(defaults | overrides)


class TestJudge:
    def test_answer_first_passes(self) -> None:
        outcome = judge(make_case(), SearchMode.HYBRID, ["H00001", "H00003"])

        assert outcome.passed
        assert outcome.answer_rank == 1
        assert outcome.reason == ""

    def test_answer_second_fails_and_names_what_beat_it(self) -> None:
        outcome = judge(make_case(), SearchMode.VECTOR, ["H00003", "H00001"])

        assert not outcome.passed
        assert outcome.answer_rank == 2
        assert "H00003 took #1" in outcome.reason

    def test_answer_absent_fails(self) -> None:
        outcome = judge(make_case(), SearchMode.VECTOR, ["H00003", "H00006"])

        assert not outcome.passed
        assert outcome.answer_rank is None
        assert "absent" in outcome.reason

    def test_empty_results_fail_without_crashing(self) -> None:
        outcome = judge(make_case(), SearchMode.VECTOR, [])

        assert not outcome.passed
        assert outcome.top_id is None

    def test_any_acceptable_answer_at_first_passes(self) -> None:
        """H00001 and its petite cut differ only in a dimension the query never
        mentions, so either at #1 is correct and neither is a regression."""
        case = make_case(answers=["H00001", "H00007"])

        assert judge(case, SearchMode.HYBRID, ["H00007", "H00001"]).passed

    def test_best_acceptable_answer_sets_the_rank(self) -> None:
        case = make_case(answers=["H00001", "H00007"])

        outcome = judge(case, SearchMode.VECTOR, ["H00003", "H00007", "H00001"])

        assert outcome.answer_rank == 2

    def test_forbidden_item_fails_even_with_the_answer_first(self) -> None:
        """This is the whole point of the filtered mode: an out-of-stock item in
        the results is a failure regardless of how good the top hit is."""
        case = make_case(forbidden=["H00004"])

        outcome = judge(case, SearchMode.VECTOR, ["H00001", "H00004"])

        assert not outcome.passed
        assert outcome.leaked == ["H00004"]
        assert "H00004 (#2)" in outcome.reason

    def test_forbidden_items_not_returned_are_not_leaks(self) -> None:
        case = make_case(forbidden=["H00004", "H00002"])

        outcome = judge(case, SearchMode.HYBRID, ["H00001", "H00003"])

        assert outcome.passed
        assert outcome.leaked == []

    def test_both_failure_reasons_are_reported_together(self) -> None:
        case = make_case(forbidden=["H00004"])

        outcome = judge(case, SearchMode.VECTOR, ["H00003", "H00001", "H00004"])

        assert "answer at #2" in outcome.reason
        assert "H00004 (#3)" in outcome.reason


class TestRegressionDetection:
    def test_matching_the_recorded_baseline_is_not_a_regression(self) -> None:
        case = make_case(expect={"text": "fail", "vector": "fail", "hybrid": "pass"})

        assert not judge(case, SearchMode.VECTOR, ["H00003", "H00001"]).regressed

    def test_getting_worse_than_the_baseline_is_a_regression(self) -> None:
        case = make_case(expect={"text": "fail", "vector": "fail", "hybrid": "pass"})

        assert judge(case, SearchMode.HYBRID, ["H00003", "H00001"]).regressed

    def test_getting_better_than_the_baseline_is_also_a_regression(self) -> None:
        """Not a bug. If vector-only starts passing the case that exists to show
        vector-only failing, the episode's argument has quietly stopped being
        true and someone needs to look at it."""
        case = make_case(expect={"text": "fail", "vector": "fail", "hybrid": "pass"})

        assert judge(case, SearchMode.VECTOR, ["H00001"]).regressed


class TestCaseValidation:
    def test_pass_and_fail_words_become_booleans(self) -> None:
        case = make_case(expect={"text": "fail", "vector": "pass", "hybrid": "pass"})

        assert case.expect[SearchMode.TEXT] is False
        assert case.expect[SearchMode.VECTOR] is True

    def test_a_missing_mode_expectation_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="every mode must be recorded"):
            make_case(expect={"text": "fail", "hybrid": "pass"})

    def test_a_case_with_no_acceptable_answer_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_case(answers=[])


class TestModeReport:
    @staticmethod
    def outcome(case_id: str, *, passed: bool, rank: int | None) -> CaseOutcome:
        return CaseOutcome(
            case_id=case_id,
            mode=SearchMode.HYBRID,
            passed=passed,
            expected=passed,
            answer_rank=rank,
        )

    def test_counts_and_mrr(self) -> None:
        report = ModeReport(
            mode=SearchMode.HYBRID,
            outcomes=[
                self.outcome("a", passed=True, rank=1),
                self.outcome("b", passed=False, rank=4),
                self.outcome("c", passed=False, rank=None),
            ],
        )

        assert (report.passed, report.total) == (1, 3)
        assert report.mrr == pytest.approx((1.0 + 0.25 + 0.0) / 3)

    def test_mrr_rewards_moving_the_answer_up_without_reaching_first(self) -> None:
        """Why MRR is here at all: the pass count cannot see this improvement."""
        deep = [self.outcome("a", passed=False, rank=9)]
        shallow = [self.outcome("a", passed=False, rank=2)]
        before = ModeReport(mode=SearchMode.VECTOR, outcomes=deep)
        after = ModeReport(mode=SearchMode.HYBRID, outcomes=shallow)

        assert before.passed == after.passed == 0
        assert after.mrr > before.mrr

    def test_empty_report_does_not_divide_by_zero(self) -> None:
        assert ModeReport(mode=SearchMode.HYBRID, outcomes=[]).mrr == 0.0
