"""Domain models. Everything crossing a boundary is typed."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SearchMode(StrEnum):
    """The three retrieval signals, in the order episode 1 introduces them.

    TEXT    — BM25 over `search_text`. Where most production search already is.
              Matches the words the shopper typed, which collapses the moment
              they do not happen to know the vocabulary the catalogue uses.
    VECTOR  — cosine similarity over embeddings. Matches meaning, so intent
              expressed in the shopper's own words still lands.
    HYBRID  — both signals fused with RRF. What real systems do, and the first
              taste of a general pattern: fuse several signals, then rank, then
              re-rank.

    Filters are deliberately NOT a mode. Price, stock, category and colour
    constraints are orthogonal to the signal and apply identically to all three
    — that is the point worth teaching, and making "filtered" a stage in a
    progression implies the opposite.
    """

    TEXT = "text"
    VECTOR = "vector"
    HYBRID = "hybrid"


class Product(BaseModel):
    """A catalogue document as stored in Redis."""

    product_id: str
    name: str
    brand: str
    category: str
    department: str = "Women"
    price: float
    cost: float | None = None
    in_stock: bool
    is_hero: bool = False

    description: str = ""
    material: str = "unspecified"
    fit: str = "regular"
    sizes: list[str] = Field(default_factory=list)
    colours: list[str] = Field(default_factory=list)
    waterproof_mm: int = 0

    search_text: str = ""

    def to_embedding_input(self) -> str:
        """Text handed to the embedding model.

        Deliberately excludes price and stock: numbers embed badly, and putting
        them here is the mistake episode 1 exists to correct.
        """
        parts = [
            self.name,
            self.brand,
            self.category,
            self.description,
            f"Material: {self.material}.",
            f"Fit: {self.fit}.",
        ]
        if self.colours:
            parts.append("Colours: " + ", ".join(self.colours) + ".")
        return " ".join(p for p in parts if p)


class PolicyChunk(BaseModel):
    """One section of a store policy document."""

    policy_id: str
    title: str
    topic: str
    chunk_index: int
    body: str


class SearchFilters(BaseModel):
    """Constraints from the UI facets — these map 1:1 onto RedisVL filters."""

    max_price: float | None = None
    min_price: float | None = None
    categories: list[str] = Field(default_factory=list)
    colours: list[str] = Field(default_factory=list)
    sizes: list[str] = Field(default_factory=list)
    in_stock_only: bool = False

    def is_empty(self) -> bool:
        return not any(
            [
                self.max_price is not None,
                self.min_price is not None,
                self.categories,
                self.colours,
                self.sizes,
                self.in_stock_only,
            ]
        )


class SearchHit(BaseModel):
    """One result, with enough detail for the UI card and the dev drawer."""

    product_id: str
    name: str
    brand: str
    category: str
    price: float
    in_stock: bool
    colours: list[str] = Field(default_factory=list)
    score: float


class Timings(BaseModel):
    """Latency split by stage so the receipt attributes cost to a component."""

    embed_ms: float = 0.0
    redis_ms: float = 0.0
    llm_ms: float = 0.0

    @property
    def total_ms(self) -> float:
        return self.embed_ms + self.redis_ms + self.llm_ms


class SearchResult(BaseModel):
    """A completed search, plus what it took to produce it."""

    mode: SearchMode
    query: str
    hits: list[SearchHit]
    total: int
    timings: Timings
    redis_query: str = Field("", description="The query issued, shown in the dev drawer")
