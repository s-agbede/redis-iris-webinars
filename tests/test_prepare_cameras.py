import pytest

from scripts.prepare_cameras import select_records, verify_source_rows


def test_rebuild_rejects_lost_candidates_and_changed_source_values() -> None:
    canonical = [{"query_id": 1, "product_id": "A"}, {"query_id": 1, "product_id": "B"}]
    verify_source_rows(list(reversed(canonical)), canonical, "judgements")
    with pytest.raises(ValueError, match="pinned source"):
        verify_source_rows(canonical[:1], canonical, "judgements")
    with pytest.raises(ValueError, match="pinned source"):
        verify_source_rows(
            [canonical[0], {**canonical[1], "product_id": "C"}], canonical, "judgements"
        )


def test_selection_retains_every_judged_candidate_without_inventing_fields() -> None:
    products = [
        {"product_id": "A", "product_locale": "us", "product_title": "Camera"},
        {"product_id": "B", "product_locale": "us", "product_title": "Unrelated book"},
        {"product_id": "C", "product_locale": "us", "product_title": "Excluded query's lens"},
    ]
    examples = [
        {"query_id": 1, "product_id": "A", "product_locale": "us", "esci_label": "E"},
        {"query_id": 1, "product_id": "B", "product_locale": "us", "esci_label": "I"},
        {"query_id": 2, "product_id": "C", "product_locale": "us", "esci_label": "E"},
    ]
    selected, judgements = select_records(iter(products), iter(examples), {1})
    assert selected == products[:2]
    assert judgements == examples[:2]
    with pytest.raises(ValueError, match="missing"):
        select_records(iter(products[:1]), iter(examples), {1})
