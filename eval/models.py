"""Keep incomplete source judgements separate from a small human-reviewed pool."""

from typing import Literal

from pydantic import BaseModel, Field

from app.models import SearchHit


class ReviewedCase(BaseModel):
    case_id: str
    query: str
    notes: str
    brands: list[str] = Field(default_factory=list)
    judgements: dict[str, Literal["relevant", "irrelevant"]] = Field(default_factory=dict)


class Assessment(BaseModel):
    source_judged: int
    source_unjudged: int
    first_source_exact_rank: int | None
    reviewed_top_label: Literal["relevant", "irrelevant", "unreviewed", "no_results"]


def assess(hits: list[SearchHit], case: ReviewedCase | None = None) -> Assessment:
    judged = sum(hit.source_label is not None for hit in hits)
    top_label: Literal["relevant", "irrelevant", "unreviewed", "no_results"] = "no_results"
    if hits:
        top_label = case.judgements.get(hits[0].product_id, "unreviewed") if case else "unreviewed"
    return Assessment(
        source_judged=judged,
        source_unjudged=len(hits) - judged,
        first_source_exact_rank=next(
            (i for i, hit in enumerate(hits, 1) if hit.source_label == "E"), None
        ),
        reviewed_top_label=top_label,
    )
