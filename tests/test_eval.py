from app.models import PassageEvidence, SearchHit
from eval.models import ReviewedCase, assess


def hit(pid: str, label: str | None = None) -> SearchHit:
    return SearchHit.model_validate(
        {
            "product_id": pid,
            "title": pid,
            "brand": None,
            "color": None,
            "score": 1,
            "source_label": label,
            "passage": PassageEvidence(
                passage_id=pid, field="product_title", text=pid, start=0, end=len(pid)
            ).model_dump(),
        }
    )


def test_unjudged_products_are_reported_separately_from_irrelevant() -> None:
    result = assess([hit("a"), hit("b", "I"), hit("c", "E")])
    assert result.source_judged == 2
    assert result.source_unjudged == 1
    assert result.first_source_exact_rank == 3
    assert result.reviewed_top_label == "unreviewed"


def test_human_review_is_kept_separate_from_original_dataset_label() -> None:
    case = ReviewedCase(
        case_id="model",
        query="T7i",
        notes="T8i is a different model",
        judgements={"t8i": "irrelevant"},
    )
    result = assess([hit("t8i", "E")], case)
    assert result.first_source_exact_rank == 1
    assert result.reviewed_top_label == "irrelevant"


def test_new_top_product_is_unreviewed_and_not_automatically_a_failure() -> None:
    case = ReviewedCase(
        case_id="model", query="lens", notes="Limited reviewed pool", judgements={"a": "relevant"}
    )
    result = assess([hit("new")], case)
    assert result.reviewed_top_label == "unreviewed"


def test_empty_ranking_has_no_exact_rank_or_invented_judgements() -> None:
    result = assess([])
    assert result.source_judged == result.source_unjudged == 0
    assert result.first_source_exact_rank is None
    assert result.reviewed_top_label == "no_results"


def test_target_rank_and_review_coverage_are_reported_separately() -> None:
    case = ReviewedCase(case_id="sony", query="sony zv e10", notes="Camera, not accessory",
                        judgements={"camera": "relevant", "strap": "irrelevant"}, required_top_k=3)
    result = assess([hit("strap"), hit("unknown"), hit("camera")], case)
    assert result.first_reviewed_relevant_rank == 3
    assert result.reciprocal_rank == 1 / 3
    assert result.reviewed_relevant == 1
    assert result.reviewed_irrelevant == 1
    assert result.reviewed_unjudged == 1
    assert result.expectation_passed is True


def test_missing_target_fails_explicit_expectation_without_labelling_unknown_irrelevant() -> None:
    case = ReviewedCase(case_id="sony", query="sony", notes="Known target",
                        judgements={"camera": "relevant"}, required_top_k=1)
    result = assess([hit("unknown"), hit("camera")], case)
    assert result.expectation_passed is False
    assert result.reviewed_irrelevant == 0
    assert result.reviewed_unjudged == 1
    empty = assess([], case)
    assert empty.expectation_passed is False
    assert empty.reciprocal_rank == 0


def test_no_reviewed_targets_means_no_quality_claim() -> None:
    result = assess([hit("unknown")])
    assert result.expectation_passed is None
    assert result.reciprocal_rank is None
