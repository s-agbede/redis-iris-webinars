from app.shop.jev import JevDecision, JevError
from eval.cache import CacheCase, evaluate, load_cases


def test_camera_cases_have_both_reusable_and_unsuitable_answers():
    cases = load_cases()
    assert len(cases) >= 8
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.expected_reuse for case in cases} == {True, False}


def test_report_counts_actual_reuse_after_confidence_gate_and_errors():
    cases = [
        CacheCase(
            case_id=str(i),
            expected_reuse=(i < 2),
            question="Explain aperture",
            answer="Lens opening.",
        )
        for i in range(4)
    ]
    answers = iter(
        [
            JevDecision(
                choice="accept",
                confidence=0.9,
                probabilities={"accept": 0.95, "reject": 0.025, "uncertain": 0.025},
            ),
            JevDecision(
                choice="accept",
                confidence=0.1,
                probabilities={"accept": 0.4, "reject": 0.3, "uncertain": 0.3},
            ),
            JevDecision(
                choice="accept",
                confidence=0.9,
                probabilities={"accept": 0.95, "reject": 0.025, "uncertain": 0.025},
            ),
            JevError("invalid response"),
        ]
    )

    def verify(state):
        result = next(answers)
        if isinstance(result, Exception):
            raise result
        return result

    report = evaluate(cases, verify, confidence=0.5)
    assert report.valid_reuses == 1
    assert report.missed_valid_reuses == 1
    assert report.unsuitable_reuses == 1
    assert report.errors == 1
    assert report.provider_cost_usd is None
