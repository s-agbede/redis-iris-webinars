"""Conservative verdicts must not confuse missing extraction with PII exclusion."""

import pytest

from app.shop.memory import MemoryEvent, MemoryRecord, MemorySession

EMAIL = "ram-demo-abc123@example.invalid"


def memory(memory_id: str, text: str) -> MemoryRecord:
    return MemoryRecord(id=memory_id, text=text, memory_type="semantic", owner_id="eval-owner")


def test_empty_inventory_does_not_pass_exclusion_or_reconciliation() -> None:
    from scripts.evaluate_shop_memory import evaluate_records

    checks = evaluate_records([], EMAIL)
    assert checks.reconciliation.status == "pending"
    assert checks.pii_exclusion.status == "pending"


def test_clear_corrected_ownership_and_useful_fact_confirm_checks() -> None:
    from scripts.evaluate_shop_memory import evaluate_records

    checks = evaluate_records(
        [
            memory("camera", "User currently owns a Canon EOS R50."),
            memory("preference", "User prefers purple camera straps with tiny yellow ducks."),
        ],
        EMAIL,
    )
    assert checks.reconciliation.status == "confirmed"
    assert checks.reconciliation.evidence_ids == ["camera"]
    assert checks.pii_exclusion.status == "confirmed"
    assert checks.pii_exclusion.evidence_ids == ["preference"]


@pytest.mark.parametrize(
    "text",
    [
        "User does not own a Canon EOS R50.",
        "User used to own a Canon EOS R50.",
        "User wants to buy a Canon EOS R50.",
        "User currently owns a Canon EOS R50, but sold it yesterday.",
    ],
)
def test_ambiguous_or_negative_ownership_never_passes(text: str) -> None:
    from scripts.evaluate_shop_memory import evaluate_records

    checks = evaluate_records([memory("candidate", text)], EMAIL)
    assert checks.reconciliation.status == "manual_review"


@pytest.mark.parametrize(
    "text",
    [
        "User no longer prefers purple camera straps with tiny yellow ducks.",
        "User dislikes purple camera straps with tiny yellow ducks.",
        "User prefers purple camera straps with tiny yellow ducks, but that preference changed.",
    ],
)
def test_negative_or_ambiguous_preference_never_passes_exclusion(text: str) -> None:
    from scripts.evaluate_shop_memory import evaluate_records

    checks = evaluate_records([memory("candidate", text)], EMAIL)
    assert checks.pii_exclusion.status == "manual_review"


def test_stale_current_ownership_keeps_reconciliation_pending() -> None:
    from scripts.evaluate_shop_memory import evaluate_records

    checks = evaluate_records(
        [
            memory("old", "User currently owns a Sony a6400."),
            memory("new", "User currently owns a Canon EOS R50."),
        ],
        EMAIL,
    )
    assert checks.reconciliation.status == "pending"
    assert set(checks.reconciliation.evidence_ids) == {"old", "new"}


def test_historical_sony_is_preserved_for_human_review() -> None:
    from scripts.evaluate_shop_memory import evaluate_records

    checks = evaluate_records(
        [
            memory("old", "User sold their Sony a6400."),
            memory("new", "User currently owns a Canon EOS R50."),
        ],
        EMAIL,
    )
    assert checks.reconciliation.status == "manual_review"


def test_conflicting_preference_records_require_review() -> None:
    from scripts.evaluate_shop_memory import evaluate_records

    checks = evaluate_records(
        [
            memory("positive", "User prefers purple camera straps with tiny yellow ducks."),
            memory("negative", "User no longer likes purple camera straps with tiny yellow ducks."),
        ],
        EMAIL,
    )
    assert checks.pii_exclusion.status == "manual_review"


@pytest.mark.parametrize("leak", [EMAIL, EMAIL.upper(), "Contact local part: ram-demo-abc123"])
def test_fictional_email_leak_fails_even_when_useful_fact_is_present(leak: str) -> None:
    from scripts.evaluate_shop_memory import evaluate_records

    checks = evaluate_records(
        [
            memory("useful", "User prefers purple camera straps with tiny yellow ducks."),
            memory("leak", leak),
        ],
        EMAIL,
    )
    assert checks.pii_exclusion.status == "failed"
    assert checks.pii_exclusion.evidence_ids == ["leak"]


def test_isolation_requires_both_inventory_and_semantic_recall_to_be_empty() -> None:
    from scripts.evaluate_shop_memory import evaluate_isolation

    assert evaluate_isolation([], []).status == "confirmed"
    assert evaluate_isolation([], [memory("leaked", "Camera fact")]).status == "failed"
    assert evaluate_isolation([memory("leaked", "Camera fact")], []).status == "failed"


def test_new_session_must_have_neither_events_nor_summary() -> None:
    from scripts.evaluate_shop_memory import evaluate_new_session

    assert evaluate_new_session(MemorySession()).status == "confirmed"
    assert evaluate_new_session(MemorySession(summary="Earlier context")).status == "failed"
    session = MemorySession(events=[MemoryEvent(event_id="e1", role="USER", text="Camera")])
    assert evaluate_new_session(session).status == "failed"


def test_overall_result_never_promotes_pending_or_manual_review_to_confirmed() -> None:
    from scripts.evaluate_shop_memory import CheckResult, overall_status

    confirmed = CheckResult(status="confirmed", reason="Observed")
    pending = CheckResult(status="pending", reason="Not yet extracted")
    manual = CheckResult(status="manual_review", reason="Ambiguous wording")
    failed = CheckResult(status="failed", reason="Leaked")
    assert overall_status([confirmed, confirmed]) == "confirmed"
    assert overall_status([confirmed, pending]) == "pending"
    assert overall_status([confirmed, manual]) == "manual_review"
    assert overall_status([pending, failed]) == "failed"
