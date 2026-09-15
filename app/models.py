"""Source records and typed HTTP/search boundaries for the comparison lab."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Label = Literal["E", "S", "C", "I"]
SourceField = Literal["product_title", "product_description", "product_bullet_point"]


class SearchMode(StrEnum):
    BASIC = "basic"
    TEXT = "text"
    VECTOR = "vector"
    HYBRID = "hybrid"


class CameraProduct(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: str
    product_title: str
    product_description: str | None = None
    product_bullet_point: str | None = None
    product_brand: str | None = None
    product_color: str | None = None
    product_locale: Literal["us"] = "us"


class PassageEvidence(BaseModel):
    passage_id: str
    field: SourceField
    text: str
    start: int
    end: int


class Passage(PassageEvidence):
    product_id: str
    title: str
    brand: str
    color: str
    search_text: str


class Judgement(BaseModel):
    query: str
    query_id: int
    product_id: str
    product_locale: Literal["us"]
    esci_label: Label
    split: Literal["train", "test"]


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=1000)
    brands: list[str] = Field(default_factory=list, max_length=20)
    num_results: int = Field(default=5, ge=1, le=20)
    include_basic: bool = False

    @field_validator("query")
    @classmethod
    def nonblank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a search query.")
        return value.strip()

    @field_validator("brands")
    @classmethod
    def valid_brands(cls, values: list[str]) -> list[str]:
        if any(not value.strip() or len(value) > 300 for value in values):
            raise ValueError("Brand filters must contain nonempty source values.")
        return list(dict.fromkeys(values))


class ProductPhoto(BaseModel):
    """Attributed enrichment, separate from the original ESCI source record."""

    model_config = ConfigDict(extra="forbid")
    url: str = Field(pattern=r"^/photos/[a-z0-9-]+\.jpg$")
    alt: str = Field(min_length=1)
    caption: str = Field(min_length=1)
    source_url: str = Field(pattern=r"^https://")
    author: str = Field(min_length=1)
    license: str = Field(min_length=1)
    license_url: str = Field(pattern=r"^https://")


class TextSpan(BaseModel):
    start: int
    end: int


class FusionEvidence(BaseModel):
    constant: int = 60
    window: int
    text_rank: int | None = None
    vector_rank: int | None = None
    text_contribution: float | None = None
    vector_contribution: float | None = None
    reconstructed_score: float | None = None
    status: Literal["verified", "unavailable"] = "unavailable"
    note: str


class SearchHit(BaseModel):
    product_id: str
    title: str
    brand: str | None
    color: str | None
    score: float
    source_label: Label | None = None
    passage: PassageEvidence
    photo: ProductPhoto | None = None
    indexed_text: str = ""
    lexical_matches: list[TextSpan] = Field(
        default_factory=list,
        description=(
            "Literal query-word overlap in indexed_text, using Unicode code-point offsets. "
            "Application annotations, not Redis-reported match offsets or BM25 attribution."
        ),
    )
    title_matches: list[TextSpan] = Field(
        default_factory=list,
        description="Literal query-word overlap in title, using Unicode code-point offsets.",
    )
    passage_matches: list[TextSpan] = Field(
        default_factory=list,
        description="Literal query-word overlap in passage.text, using Unicode code-point offsets.",
    )
    passage_rank: int = 1
    fusion: FusionEvidence | None = None


class ModeResult(BaseModel):
    mode: SearchMode
    query_ms: float
    score_kind: str
    redis_query: str
    hits: list[SearchHit] = Field(default_factory=list)
    error: str | None = None


class Comparison(BaseModel):
    query: str
    brands: list[str]
    embedding_ms: float
    total_ms: float
    explanation_ms: float = 0
    embedding_model: str
    source_revision: str
    candidate_limit: int
    results: list[ModeResult]


class ProductDetail(CameraProduct):
    source_revision: str
    passages: list[PassageEvidence]
    photo: ProductPhoto | None = None


class FacetValue(BaseModel):
    value: str
    count: int


class ExampleQuery(BaseModel):
    query: str
    title: str
    kind: Literal["exact", "intent", "constraint"]
    origin: Literal["esci", "authored"]


class CatalogInfo(BaseModel):
    name: str = "Camera Search Lab"
    product_count: int
    passage_count: int
    source_revision: str
    embedding_model: str
    embedding_revision: str
    vector_dimensions: int
    index_algorithm: str
    brands: list[FacetValue]
    examples: list[ExampleQuery]
