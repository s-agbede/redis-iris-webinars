"""Preserve source listings and derive bounded, traceable retrieval passages."""

import gzip
import hashlib
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from pydantic import BaseModel
from tokenizers import Tokenizer

from app.models import CameraProduct, Judgement, Label, Passage, SourceField


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden += 1
        self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.hidden:
            self.hidden -= 1
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def clean_text(value: str | None) -> str:
    parser = _TextExtractor()
    parser.feed(value or "")
    return re.sub(r"\s+", " ", "".join(parser.parts)).strip()


def make_passages(
    product: CameraProduct, tokenizer: Tokenizer, max_tokens: int = 240, overlap: int = 32
) -> list[Passage]:
    """Offsets refer to cleaned source fields. Every searchable source token is retained."""
    title = clean_text(product.product_title)
    prefix_text = " ".join(filter(None, [title, product.product_brand, product.product_color]))
    prefix_encoding = tokenizer.encode(prefix_text, add_special_tokens=False)
    prefix_count = min(48, max_tokens // 3, len(prefix_encoding.ids))
    prefix = prefix_text[: prefix_encoding.offsets[prefix_count - 1][1]] if prefix_count else ""
    budget = max_tokens - prefix_count - 4
    if budget <= overlap or overlap < 0:
        raise ValueError("Passage budget must exceed overlap after adding title context.")
    passages: list[Passage] = []
    fields: tuple[SourceField, ...] = (
        "product_title",
        "product_description",
        "product_bullet_point",
    )
    for field in fields:
        body = clean_text(getattr(product, field))
        encoding = tokenizer.encode(body, add_special_tokens=False)
        offset = 0
        while offset < len(encoding.ids):
            stop = min(offset + budget, len(encoding.ids))
            start = encoding.offsets[offset][0]
            end = encoding.offsets[stop - 1][1]
            text = body[start:end]
            search_text = f"{prefix}. {text}" if prefix else text
            while len(tokenizer.encode(search_text, add_special_tokens=False).ids) > max_tokens:
                stop -= 1
                if stop <= offset:
                    raise ValueError("Cannot fit a source token inside the passage budget.")
                end = encoding.offsets[stop - 1][1]
                text = body[start:end]
                search_text = f"{prefix}. {text}" if prefix else text
            passages.append(
                Passage(
                    passage_id=f"us:{product.product_id}:{len(passages)}",
                    product_id=product.product_id,
                    title=product.product_title,
                    brand=product.product_brand or "",
                    color=product.product_color or "",
                    field=field,
                    text=text,
                    start=start,
                    end=end,
                    search_text=search_text,
                )
            )
            if stop == len(encoding.ids):
                break
            offset = max(offset + 1, stop - overlap)
    return passages


class DataManifest(BaseModel):
    source: str
    source_revision: str
    product_count: int
    query_count: int
    judgement_count: int
    checksums: dict[str, str]


@dataclass
class Catalog:
    products: dict[str, CameraProduct]
    judgements: list[Judgement]
    manifest: DataManifest
    fingerprint: str

    @classmethod
    def load(cls, directory: Path) -> "Catalog":
        raw_manifest = (directory / "manifest.json").read_bytes()
        manifest = DataManifest.model_validate_json(raw_manifest)
        for name, expected in manifest.checksums.items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Camera data checksum mismatch: {name}.")
        with gzip.open(directory / "products.jsonl.gz", "rt") as stream:
            products = [CameraProduct.model_validate_json(line) for line in stream]
        with gzip.open(directory / "judgements.jsonl.gz", "rt") as stream:
            judgements = [Judgement.model_validate_json(line) for line in stream]
        by_id = {p.product_id: p for p in products}
        if len(by_id) != len(products) or len(products) != manifest.product_count:
            raise ValueError("Camera catalogue count or identity mismatch.")
        if len(judgements) != manifest.judgement_count:
            raise ValueError("Camera judgement count mismatch.")
        if any(j.product_id not in by_id for j in judgements):
            raise ValueError("A source judgement points to a missing product.")
        return cls(by_id, judgements, manifest, hashlib.sha256(raw_manifest).hexdigest())

    def labels(self, query: str) -> dict[str, Label]:
        # Require the source query itself, not a semantically similar query.
        return {j.product_id: j.esci_label for j in self.judgements if j.query == query}
