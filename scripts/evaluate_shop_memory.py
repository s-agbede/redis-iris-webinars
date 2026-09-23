"""Evaluate real RAM extraction in isolated demo owners; never manufacture a pass.

Run with ``uv run python -m scripts.evaluate_shop_memory --timeout 420``.
Only the initial Sony onboarding fact is written directly. Corrections and the
fictional email test are session events; Redis performs all subsequent extraction.
"""

import argparse
import re
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.shop.memory import MemoryError, MemoryGateway, MemoryRecord, MemorySession, RAMClient
from app.shop.settings import ShopSettings

Status = Literal["confirmed", "pending", "manual_review", "failed"]
INITIAL_CAMERA = "User currently owns a Sony a6400."
CORRECTION = (
    "I sold my Sony a6400 and no longer own it. "
    "My only camera now is a Canon EOS R50. Please remember my current camera."
)
PREFERENCE = "I prefer purple camera straps with tiny yellow ducks."


class CheckResult(BaseModel):
    status: Status
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)


class MemoryChecks(BaseModel):
    reconciliation: CheckResult
    pii_exclusion: CheckResult


class Snapshot(BaseModel):
    checked_at: str
    elapsed_seconds: float
    inventory: list[MemoryRecord]
    other_owner_inventory: list[MemoryRecord]
    other_owner_recall: list[MemoryRecord]
    fresh_session_context: MemorySession
    reconciliation: CheckResult
    pii_exclusion: CheckResult
    owner_isolation: CheckResult
    fresh_session: CheckResult

    def checks(self) -> list[CheckResult]:
        return [self.reconciliation, self.pii_exclusion, self.owner_isolation, self.fresh_session]


class SubmittedEvent(BaseModel):
    event_id: str
    text: str


class EvaluationReport(BaseModel):
    run_id: str
    started_at: str
    owner_id: str
    other_owner_id: str
    session_id: str
    fresh_session_id: str
    fictional_email: str
    timeout_seconds: float
    baseline: list[MemoryRecord] = Field(default_factory=list)
    events: list[SubmittedEvent] = Field(default_factory=list)
    snapshots: list[Snapshot] = Field(default_factory=list)
    status: Status = "pending"
    deadline_reached: bool = False
    finished_at: str | None = None
    error: str | None = None
    scope: str = (
        "RAM service evaluation using isolated owners. It does not evaluate chat model answers, "
        "catalogue grounding or Playbook. Confirmed PII exclusion means the submitted fictional "
        "email/local marker was absent from record text across observed full inventories while "
        "its useful fact was present. Structured custom-type attributes are not exposed by this "
        "application boundary. This is not a general guarantee about PII or future extraction."
    )


def _normalise(text: str) -> str:
    return " ".join(text.casefold().replace("’", "'").split()).rstrip(". ")


def _current_camera(text: str, camera: str) -> bool:
    name = re.escape(camera.casefold())
    patterns = [
        rf"(?:the )?user (?:currently |now )?owns (?:only )?(?:a |the )?{name}(?: camera)?",
        rf"(?:the )?user's (?:only |current )?camera (?:now )?is (?:a |the )?{name}",
    ]
    return any(re.fullmatch(pattern, _normalise(text)) for pattern in patterns)


def _affirmative_preference(text: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:the )?user prefers purple camera straps with tiny yellow ducks", _normalise(text)
        )
    )


def evaluate_records(records: Sequence[MemoryRecord], email: str) -> MemoryChecks:
    """Use narrow affirmative grammars; ambiguous natural language needs review.

    Whole-record matches prevent a negation or qualification after an otherwise
    positive clause from being treated as success. Historical Sony facts may be
    legitimate, so their presence requests review instead of being labelled stale.
    """
    camera_records = [
        m for m in records if "canon" in m.text.casefold() or "sony" in m.text.casefold()
    ]
    canon = [m for m in camera_records if _current_camera(m.text, "Canon EOS R50")]
    stale = [m for m in camera_records if _current_camera(m.text, "Sony a6400")]
    if stale:
        reconciliation = CheckResult(
            status="pending",
            reason="A clear current-ownership Sony fact still exists.",
            evidence_ids=[m.id for m in camera_records],
        )
    elif canon and len(canon) == len(camera_records):
        reconciliation = CheckResult(
            status="confirmed",
            reason="Clear current Canon ownership is present; no Sony record remains.",
            evidence_ids=[m.id for m in canon],
        )
    elif camera_records:
        reconciliation = CheckResult(
            status="manual_review",
            reason="Review camera wording, negation and historical Sony facts.",
            evidence_ids=[m.id for m in camera_records],
        )
    else:
        reconciliation = CheckResult(
            status="pending", reason="No clear corrected camera fact has appeared."
        )

    local_part = email.casefold().split("@", 1)[0]
    leaked = [m for m in records if local_part in m.text.casefold()]
    preferences = [
        m for m in records if "purple" in m.text.casefold() or "yellow ducks" in m.text.casefold()
    ]
    affirmative = [m for m in preferences if _affirmative_preference(m.text)]
    if leaked:
        pii = CheckResult(
            status="failed",
            reason="The fictional email or its unique local part remains in long-term memory.",
            evidence_ids=[m.id for m in leaked],
        )
    elif affirmative and len(affirmative) == len(preferences):
        pii = CheckResult(
            status="confirmed",
            reason="Useful preference was extracted; the fictional email/local marker is absent.",
            evidence_ids=[m.id for m in affirmative],
        )
    elif preferences:
        pii = CheckResult(
            status="manual_review",
            reason="Email is absent, but useful preference wording needs review.",
            evidence_ids=[m.id for m in preferences],
        )
    else:
        pii = CheckResult(
            status="pending",
            reason="Email absence alone is insufficient: the useful fact has not appeared.",
        )
    return MemoryChecks(reconciliation=reconciliation, pii_exclusion=pii)


def evaluate_isolation(
    inventory: Sequence[MemoryRecord], recall: Sequence[MemoryRecord]
) -> CheckResult:
    records = [*inventory, *recall]
    return CheckResult(
        status="failed" if records else "confirmed",
        reason=(
            "The untouched second owner unexpectedly returned memories."
            if records
            else "Both inventory and semantic recall are empty for the untouched second owner."
        ),
        evidence_ids=list(dict.fromkeys(m.id for m in records)),
    )


def evaluate_new_session(session: MemorySession) -> CheckResult:
    empty = not session.events and not session.summary
    return CheckResult(
        status="confirmed" if empty else "failed",
        reason="The new session has no events or summary."
        if empty
        else "The new session contains unexpected context.",
        evidence_ids=[event.event_id for event in session.events],
    )


def overall_status(checks: Sequence[CheckResult]) -> Status:
    for status in ("failed", "manual_review", "pending"):
        if any(check.status == status for check in checks):
            return status
    return "confirmed" if checks else "pending"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _save(report: EvaluationReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(report.model_dump_json(indent=2) + "\n")
    temporary.replace(output)


def run_evaluation(
    memory: MemoryGateway, output: Path, *, timeout: float = 420, poll_interval: float = 10
) -> EvaluationReport:
    """Preserve every full inventory and event ID, including on deadline or failure."""
    run_id = uuid4().hex
    report = EvaluationReport(
        run_id=run_id,
        started_at=_now(),
        owner_id=f"shop-eval-{run_id}",
        other_owner_id=f"shop-other-{run_id}",
        session_id=f"shop-eval-session-{run_id}",
        fresh_session_id=f"shop-eval-fresh-{run_id}",
        fictional_email=f"ram-demo-{run_id}@example.invalid",
        timeout_seconds=timeout,
    )
    _save(report, output)
    started = monotonic()
    deadline = started + timeout
    try:
        if memory.inventory(report.owner_id) or memory.session(report.session_id).events:
            raise MemoryError(
                "The isolated evaluation identifiers unexpectedly already contain data."
            )
        memory.create_facts(report.owner_id, {"camera": INITIAL_CAMERA})
        report.baseline = memory.inventory(report.owner_id)
        if not any(m.text == INITIAL_CAMERA for m in report.baseline):
            raise MemoryError("Initial Sony onboarding fact was not visible in the full inventory.")
        _save(report, output)
        for text in [
            CORRECTION,
            f"My fictional contact email is {report.fictional_email}. {PREFERENCE}",
        ]:
            event_id = memory.append_event(report.session_id, report.owner_id, "USER", text)
            report.events.append(SubmittedEvent(event_id=event_id, text=text))
            _save(report, output)
        while True:
            inventory = memory.inventory(report.owner_id)
            other_inventory = memory.inventory(report.other_owner_id)
            other_recall = memory.search(
                report.other_owner_id, "What camera do I own and what straps do I prefer?"
            )
            fresh_context = memory.session(report.fresh_session_id)
            checks = evaluate_records(inventory, report.fictional_email)
            snapshot = Snapshot(
                checked_at=_now(),
                elapsed_seconds=round(monotonic() - started, 2),
                inventory=inventory,
                other_owner_inventory=other_inventory,
                other_owner_recall=other_recall,
                fresh_session_context=fresh_context,
                reconciliation=checks.reconciliation,
                pii_exclusion=checks.pii_exclusion,
                owner_isolation=evaluate_isolation(other_inventory, other_recall),
                fresh_session=evaluate_new_session(fresh_context),
            )
            report.snapshots.append(snapshot)
            # A leakage observed earlier cannot be erased by a later clean snapshot.
            failures = [
                check
                for item in report.snapshots
                for check in item.checks()
                if check.status == "failed"
            ]
            report.status = overall_status([*snapshot.checks(), *failures])
            report.deadline_reached = monotonic() >= deadline
            _save(report, output)
            print(
                f"{snapshot.elapsed_seconds:.0f}s: reconciliation={checks.reconciliation.status}, "
                f"PII exclusion={checks.pii_exclusion.status}, "
                f"owner isolation={snapshot.owner_isolation.status}, "
                f"new session={snapshot.fresh_session.status}",
                flush=True,
            )
            if report.status == "confirmed" or report.deadline_reached:
                break
            sleep(min(poll_interval, max(0, deadline - monotonic())))
    except MemoryError as exc:
        report.status, report.error = "failed", str(exc)
    except KeyboardInterrupt:
        report.error = "Evaluation interrupted; the saved evidence is incomplete."
    finally:
        report.finished_at = _now()
        _save(report, output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--timeout", type=float, default=420, help="Total polling deadline in seconds."
    )
    parser.add_argument(
        "--poll-interval", type=float, default=10, help="Seconds between inventory reads (1–60)."
    )
    parser.add_argument(
        "--output", type=Path, help="JSON evidence path; defaults to a unique file in /tmp."
    )
    args = parser.parse_args()
    if args.timeout <= 0 or not 1 <= args.poll_interval <= 60:
        parser.error("--timeout must be positive; --poll-interval must be between 1 and 60.")
    settings = ShopSettings()
    missing = [key for key in settings.missing() if key.startswith("AGENT_MEMORY_")]
    if missing:
        parser.error("Configure " + ", ".join(missing) + " in .env.")
    output = args.output or Path(f"/tmp/shop-memory-evaluation-{uuid4().hex}.json")
    with RAMClient(
        settings.agent_memory_base_url,
        settings.agent_memory_store_id,
        settings.agent_memory_api_key.get_secret_value(),
        namespace_id=settings.agent_memory_namespace_id,
    ) as memory:
        report = run_evaluation(
            memory, output, timeout=args.timeout, poll_interval=args.poll_interval
        )
    print(f"Result: {report.status}; evidence: {output.resolve()}")
    if report.error:
        print(report.error, file=sys.stderr)
    if report.deadline_reached and report.status != "confirmed":
        print(
            "The deadline ended without automatic confirmation. "
            "Inspect the saved before/after records."
        )
    sys.exit(0 if report.status == "confirmed" else 1 if report.status == "failed" else 2)


if __name__ == "__main__":
    main()
