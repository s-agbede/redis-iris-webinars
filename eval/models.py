"""Types for the retrieval eval, and the judging rule.

Kept apart from the runner so the interesting logic — deciding whether a ranking
is correct — is testable without Redis, an OpenAI key, or a seeded index.

The judging rule is deliberately strict and deliberately simple:

    a case passes when an acceptable answer is ranked first, and nothing
    forbidden appears anywhere in the results.

Strict, because "roughly in the top five" is not what a shopper sees. Simple,
because a metric nobody can explain on a call is a metric nobody trusts.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models import SearchFilters, SearchMode

# `pass`/`fail` in the YAML reads better than true/false when the file is on
# screen, and the file is on screen — it is the argument the episode makes.
VERDICT_WORDS = {"pass": True, "fail": False}


class EvalCase(BaseModel):
    """One labelled query: what we asked, and what a good answer looks like.

    Attributes:
        case_id: Stable slug, used as the row label in the report.
        query: The text a shopper types.
        why: What this case is testing. Mirrors the `demo_role` on the hero
            product it targets, so the eval and the seed data cannot drift apart
            silently.
        filters: The facets the UI would have set. Ignored by VECTOR mode on
            purpose — that omission is the failure the other modes fix.
        answers: Product ids that are all equally correct at rank 1. A list
            rather than a single id because the catalogue contains genuinely
            interchangeable pairs (H00001 and its petite cut, H00007, differ
            only in a dimension this episode's query never mentions), and a
            coin-flip between two right answers is not a regression.
        forbidden: Product ids that must not appear at all — the out-of-stock
            parka, the over-budget shell. These are what filters are for.
        expect: Per-mode expected verdict, recorded from an observed run. This
            is the regression guard, and it cuts both ways: hybrid silently
            getting worse breaks the demo, and vector silently getting better
            breaks the story the demo tells.
    """

    case_id: str
    query: str
    why: str
    filters: SearchFilters = Field(default_factory=SearchFilters)
    answers: list[str] = Field(min_length=1)
    forbidden: list[str] = Field(default_factory=list)
    expect: dict[SearchMode, bool]

    @field_validator("expect", mode="before")
    @classmethod
    def _accept_verdict_words(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        return {
            key: VERDICT_WORDS.get(word, word) if isinstance(word, str) else word
            for key, word in value.items()
        }

    @model_validator(mode="after")
    def _require_every_mode(self) -> EvalCase:
        missing = [mode for mode in SearchMode if mode not in self.expect]
        if missing:
            raise ValueError(
                f"case {self.case_id!r} has no expectation for "
                f"{', '.join(sorted(missing))} — every mode must be recorded, "
                "including the ones that are supposed to fail"
            )
        return self


class CaseOutcome(BaseModel):
    """What one case actually did in one mode."""

    case_id: str
    mode: SearchMode
    passed: bool
    expected: bool
    answer_rank: int | None = Field(None, description="1-based; None if absent entirely")
    top_id: str | None = None
    leaked: list[str] = Field(default_factory=list)
    reason: str = ""

    @property
    def regressed(self) -> bool:
        """True when reality and the recorded baseline disagree, either way."""
        return self.passed is not self.expected

    @property
    def reciprocal_rank(self) -> float:
        return 1.0 / self.answer_rank if self.answer_rank else 0.0


class ModeReport(BaseModel):
    """Every case, run in one mode. The row that goes on the slide."""

    mode: SearchMode
    outcomes: list[CaseOutcome]

    @property
    def total(self) -> int:
        return len(self.outcomes)

    @property
    def passed(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.passed)

    @property
    def mrr(self) -> float:
        """Mean reciprocal rank of the best acceptable answer.

        Kept alongside the pass count because pass/fail is binary and hides
        progress: a mode that moves the right answer from rank 9 to rank 2 has
        improved, and the pass count alone would call that a no-op.
        """
        if not self.outcomes:
            return 0.0
        return sum(outcome.reciprocal_rank for outcome in self.outcomes) / len(self.outcomes)

    @property
    def regressions(self) -> list[CaseOutcome]:
        return [outcome for outcome in self.outcomes if outcome.regressed]


def judge(case: EvalCase, mode: SearchMode, ranked_ids: Sequence[str]) -> CaseOutcome:
    """Score one ranking against one case.

    Args:
        case: The labelled query.
        mode: The mode that produced this ranking, for the report.
        ranked_ids: Product ids in the order the search returned them.

    Returns:
        The outcome, including a human-readable reason when it failed. The
        reason is the whole point on a live call — "failed" tells you nothing,
        "the packable rain coat is #1 and the answer is #2" tells you what the
        next mode has to fix.
    """
    positions = {pid: rank for rank, pid in enumerate(ranked_ids, start=1)}
    answer_rank = min((positions[pid] for pid in case.answers if pid in positions), default=None)
    leaked = [pid for pid in case.forbidden if pid in positions]
    top_id = ranked_ids[0] if ranked_ids else None
    passed = answer_rank == 1 and not leaked

    reasons: list[str] = []
    if answer_rank is None:
        reasons.append("answer absent from results")
    elif answer_rank != 1:
        reasons.append(f"answer at #{answer_rank}, {top_id} took #1")
    if leaked:
        reasons.append(
            "filtered-out items present: "
            + ", ".join(f"{pid} (#{positions[pid]})" for pid in leaked)
        )

    return CaseOutcome(
        case_id=case.case_id,
        mode=mode,
        passed=passed,
        expected=case.expect[mode],
        answer_rank=answer_rank,
        top_id=top_id,
        leaked=leaked,
        reason="; ".join(reasons),
    )
