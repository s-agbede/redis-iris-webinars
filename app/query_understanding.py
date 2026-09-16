"""Conservative brand rules: abstain when a request could mean compatibility or comparison."""

import re
from collections.abc import Iterable

AMBIGUOUS = re.compile(
    r"\b(compatible|compatibility|fits?|mount|adapter|adaptors?|versus|vs|or|not|except|"
    r"alternatives?|instead|replacement|replaces?|similar|like)\b",
    re.IGNORECASE,
)
INTRO = re.compile(
    r"^(?:(?:show me|find me|find|i want|i need|looking for)\s+)?(?:an?\s+)?",
    re.IGNORECASE,
)


def infer_brand(query: str, known_brands: Iterable[str]) -> list[str]:
    """Infer one leading catalogue brand; keep ambiguous wording as relevance text."""
    if AMBIGUOUS.search(query):
        return []
    text = INTRO.sub("", query.strip(), count=1)
    brands = sorted(set(known_brands), key=lambda brand: (-len(brand), brand))
    mentioned = [
        brand
        for brand in brands
        if len(brand) >= 3
        and re.search(r"(?<!\w)" + re.escape(brand) + r"(?=\W|$)", text, re.IGNORECASE)
    ]
    if len(mentioned) != 1:
        return []
    for brand in mentioned:
        if len(brand) >= 3 and re.match(re.escape(brand) + r"(?=\W|$)", text, re.IGNORECASE):
            return [brand]
    return []
