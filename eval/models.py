"""Keep incomplete source judgements separate from a small assistant-reviewed catalogue pool."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models import SearchHit, SearchMode


class ReviewedCase(BaseModel):
    case_id: str
    query: str
    notes: str
    target_product: str | None = None
    required_top_k: int | None = Field(default=None, ge=1, le=5)
    required_modes: list[SearchMode] = Field(default_factory=list)
    brands: list[str] = Field(default_factory=list)
    judgements: dict[str, Literal["relevant", "irrelevant"]] = Field(default_factory=dict)


class Assessment(BaseModel):
    first_reviewed_relevant_rank: int | None
    reciprocal_rank: float | None
    reviewed_relevant: int
    reviewed_irrelevant: int
    reviewed_unjudged: int
    expectation_passed: bool | None
    source_judged: int
    source_unjudged: int
    first_source_exact_rank: int | None
    reviewed_top_label: Literal["relevant", "irrelevant", "unreviewed", "no_results"]


def assess(hits: list[SearchHit], case: ReviewedCase | None = None) -> Assessment:
    judged = sum(hit.source_label is not None for hit in hits)
    top_label: Literal["relevant", "irrelevant", "unreviewed", "no_results"] = "no_results"
    if hits:
        top_label = case.judgements.get(hits[0].product_id, "unreviewed") if case else "unreviewed"
    labels = [case.judgements.get(hit.product_id) if case else None for hit in hits]
    rank = next((i for i, label in enumerate(labels, 1) if label == "relevant"), None)
    has_targets = case is not None and "relevant" in case.judgements.values()
    threshold = case.required_top_k if case else None
    return Assessment(
        first_reviewed_relevant_rank=rank,
        reciprocal_rank=(1 / rank if rank else 0) if has_targets else None,
        reviewed_relevant=labels.count("relevant"),
        reviewed_irrelevant=labels.count("irrelevant"),
        reviewed_unjudged=labels.count(None),
        expectation_passed=(rank is not None and rank <= threshold)
        if threshold is not None and has_targets
        else None,
        source_judged=judged,
        source_unjudged=len(hits) - judged,
        first_source_exact_rank=next(
            (i for i, hit in enumerate(hits, 1) if hit.source_label == "E"), None
        ),
        reviewed_top_label=top_label,
    )
