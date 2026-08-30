"""Deterministic checks on generated catalogue data.

No LLM involved — these are the cheap mechanical checks that catch the failures
generation actually produces: pattern words leaking into the colour facet, sizes
outside a category's run, invented numeric claims, and copy that all reads the
same. Anything that fails is reported with its product id so it can be
regenerated rather than silently shipped.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.generate_descriptions import GROUPS, SIZE_APPAREL

ENRICHED = Path("seed/products.enriched.jsonl")

# Words that are patterns or finishes, not colours. These would render as
# nonsense facet chips in the UI.
NOT_COLOURS = {
    "striped", "stripe", "floral", "print", "printed", "multicolour", "multicolor",
    "assorted", "various", "pattern", "patterned", "plaid", "checked", "camo",
    "camouflage", "animal", "leopard", "polka", "tie-dye", "ombre", "metallic",
    "solid", "neutral", "mixed",
}

# Numeric performance claims must not appear on real-brand products.
CLAIM_PATTERNS = [
    re.compile(r"\b\d[\d,]*\s?mm\b", re.I),
    re.compile(r"\bhydrostatic\b", re.I),
    re.compile(r"\b\d+\s?denier\b", re.I),
    re.compile(r"\bthread count\b", re.I),
    # Require an explicit degree marker: bare "1239F" is a product code, not a
    # temperature rating, and the looser form produced false positives.
    re.compile(r"\b-?\d+\s?(?:°\s?[CF]|degrees?\s?(?:celsius|fahrenheit|[CF]))\b", re.I),
    re.compile(r"\bUPF\s?\d+", re.I),
    re.compile(r"\b\d+\s?gsm\b", re.I),
]

# Copy must not talk about commerce — that is the app's job, not the catalogue's.
FORBIDDEN_WORDS = re.compile(
    r"\b(price|priced|discount|sale|bargain|cheap|shipping|delivery|in stock|"
    r"out of stock|free returns|elevate your wardrobe)\b",
    re.I,
)

MIN_DESC, MAX_DESC = 80, 500


def _squash(text: str) -> str:
    """Lowercase and strip everything but alphanumerics, for figure comparison."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def check(product: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    desc = product.get("description", "")
    name_squashed = _squash(product.get("name", ""))

    if not MIN_DESC <= len(desc) <= MAX_DESC:
        problems.append(f"description length {len(desc)} outside {MIN_DESC}-{MAX_DESC}")

    for pattern in CLAIM_PATTERNS:
        if match := pattern.search(desc):
            # A figure already present in the real product name is being repeated,
            # not invented. "Ray-Ban Aviator ... Matte Gold55 mm" legitimately has
            # a 55mm lens; only figures with no source in the name are a problem.
            if _squash(match.group(0)) in name_squashed:
                continue
            problems.append(f"numeric claim on a real brand: {match.group(0)!r}")

    if match := FORBIDDEN_WORDS.search(desc):
        problems.append(f"commerce language in copy: {match.group(0)!r}")

    colours = product.get("colours") or []
    if not 1 <= len(colours) <= 4:
        problems.append(f"{len(colours)} colours, expected 1-4")
    for colour in colours:
        if colour.lower() in NOT_COLOURS:
            problems.append(f"not a colour: {colour!r}")
        elif " " in colour.strip():
            problems.append(f"multi-word colour: {colour!r}")

    _, allowed = GROUPS.get(product.get("category", ""), ("tops", SIZE_APPAREL))
    if bad := [s for s in product.get("sizes") or [] if s not in allowed]:
        problems.append(f"sizes outside category run: {bad}")
    if not product.get("sizes"):
        problems.append("no sizes")

    if product.get("waterproof_mm", 0) != 0:
        problems.append("waterproof_mm set on a real-brand product")

    if not product.get("material"):
        problems.append("no material")

    return problems


def main() -> None:
    records = [json.loads(l) for l in ENRICHED.read_text().splitlines() if l.strip()]
    print(f"checking {len(records)} records\n")

    failures: dict[str, list[str]] = {}
    for record in records:
        if problems := check(record):
            failures[record["product_id"]] = problems

    duplicates = {
        desc: count
        for desc, count in Counter(r["description"] for r in records).items()
        if count > 1
    }

    reason_counts = Counter(
        p.split(":")[0] for problems in failures.values() for p in problems
    )

    for pid, problems in list(failures.items())[:25]:
        print(f"  {pid}: {'; '.join(problems)}")
    if len(failures) > 25:
        print(f"  ... and {len(failures) - 25} more")

    print(f"\n{'-' * 60}")
    print(f"records      {len(records)}")
    print(f"failing      {len(failures)} ({len(failures) / max(len(records), 1):.1%})")
    print(f"duplicates   {len(duplicates)} repeated descriptions")
    if reason_counts:
        print("\nby reason:")
        for reason, count in reason_counts.most_common():
            print(f"  {count:>5}  {reason}")

    ids = Path("seed/failed_ids.txt")
    ids.write_text("\n".join(sorted(failures)) + "\n" if failures else "")
    print(f"\nfailing ids -> {ids}")


if __name__ == "__main__":
    main()
