"""Literal overlap annotations and verified native fusion rank reconstruction."""

import math
import re
from collections import defaultdict
from collections.abc import Collection
from typing import Any

from app.constants import RRF_CONSTANT
from app.models import FusionEvidence, TextSpan


def literal_query_matches(text: str, query: str, stopwords: Collection[str]) -> list[TextSpan]:
    """Show surface overlap, not Redis match offsets or a BM25 score explanation.

    JSON indexes reject native HIGHLIGHT. Preserve the indexed text and annotate
    whole query tokens literally, ignoring case and query-time stopwords. Redis
    stemming and tokenization can match additional terms that are not shown here.
    Offsets are Unicode code points, never HTML markup.
    """
    tokens = {
        token.strip(",").replace("“", "").replace("”", "").lower() for token in query.split()
    } - set(stopwords)
    tokens.discard("")
    if not tokens:
        return []
    alternatives = "|".join(re.escape(token) for token in sorted(tokens, key=len, reverse=True))
    return [
        TextSpan(start=match.start(), end=match.end())
        for match in re.finditer(rf"(?<!\w)(?:{alternatives})(?!\w)", text, re.IGNORECASE)
    ]


def _rank_intervals(rows: list[dict[str, Any]], field: str) -> dict[str, range]:
    """Equal returned scores identify a rank interval, never an arbitrary tie order."""
    groups: dict[float, list[str]] = defaultdict(list)
    for row in rows:
        if field in row:
            score = float(row[field])
            if not math.isfinite(score):
                raise ValueError("Non-finite native fusion branch score.")
            groups[score].append(str(row["passage_id"]))
    ranks: dict[str, range] = {}
    start = 1
    for score in sorted(groups, reverse=True):
        group = groups[score]
        interval = range(start, start + len(group))
        ranks.update((pid, interval) for pid in group)
        start += len(group)
    return ranks


def explain_fusion(rows: list[dict[str, Any]], window: int) -> dict[str, FusionEvidence]:
    """Reconcile ordinal ranks against native scores, publishing only unique solutions.

    Caller must return the entire native union (at most 2 * WINDOW rows). Score
    aliases are absent for passages outside a branch's fusion window. Redis 8.6
    consumes tied scores in distinct ordinal positions; the native fused score
    can resolve that order, but ambiguous pairs must remain unknown.
    """
    text_ranks = _rank_intervals(rows, "text_score")
    vector_ranks = _rank_intervals(rows, "vsim_score")
    result: dict[str, FusionEvidence] = {}
    for row in rows:
        pid = str(row["passage_id"])
        evidence = FusionEvidence(
            window=window,
            note="Component ranks could not be uniquely reconciled with Redis's RRF score.",
        )
        result[pid] = evidence
        if len(text_ranks) > window or len(vector_ranks) > window:
            continue
        native_score = float(row["combined_score"])
        if not math.isfinite(native_score) or native_score <= 0:
            continue
        possible_text = text_ranks.get(pid)
        possible_vector = vector_ranks.get(pid)
        if possible_text is None and possible_vector is None:
            continue
        solutions: list[tuple[int | None, int | None, float, float]] = []
        for text_rank in possible_text if possible_text is not None else [None]:
            text_part = 1 / (RRF_CONSTANT + text_rank) if text_rank is not None else 0.0
            remaining = native_score - text_part
            vector_rank: int | None = None
            if possible_vector is not None:
                if remaining <= 0:
                    continue
                vector_rank = round(1 / remaining - RRF_CONSTANT)
                if vector_rank not in possible_vector:
                    continue
            vector_part = 1 / (RRF_CONSTANT + vector_rank) if vector_rank is not None else 0.0
            if math.isclose(text_part + vector_part, native_score, rel_tol=0, abs_tol=1e-12):
                solutions.append((text_rank, vector_rank, text_part, vector_part))
                if len(solutions) > 1:
                    break
        if len(solutions) != 1:
            continue
        text_rank, vector_rank, text_part, vector_part = solutions[0]
        evidence.text_rank = text_rank
        evidence.vector_rank = vector_rank
        evidence.text_contribution = text_part
        evidence.vector_contribution = vector_part
        evidence.reconstructed_score = text_part + vector_part
        evidence.status = "verified"
        evidence.note = (
            "Reconstructed from native branch scores and checked against Redis's RRF score. "
            "Ranks refer to passages before product deduplication."
        )
    return result
