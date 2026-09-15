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
