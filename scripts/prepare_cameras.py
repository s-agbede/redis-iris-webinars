"""Reproduce the selected camera corpus from the pinned ESCI source Parquet files."""

import argparse
import gzip
import hashlib
import json
from collections import Counter
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "7916cdf6ab75a462e77f20ab40428a10923998d5"
PRODUCT_FIELDS = [
    "product_id",
    "product_title",
    "product_description",
    "product_bullet_point",
    "product_brand",
    "product_color",
    "product_locale",
]
JUDGEMENT_FIELDS = ["query", "query_id", "product_id", "product_locale", "esci_label", "split"]
Row = dict[str, Any]


def select_records(
    products: Iterable[Row], examples: Iterable[Row], query_ids: set[int]
) -> tuple[list[Row], list[Row]]:
    """Select by reviewed queries, including their irrelevant and substitute candidates."""
    judgements = [
        row for row in examples if row["product_locale"] == "us" and row["query_id"] in query_ids
    ]
    found_queries = {row["query_id"] for row in judgements}
    if found_queries != query_ids:
        raise ValueError(f"Source examples are missing {len(query_ids - found_queries)} queries")
    wanted = {row["product_id"] for row in judgements}
    selected = [
        row for row in products if row["product_locale"] == "us" and row["product_id"] in wanted
    ]
    found = {row["product_id"] for row in selected}
    if found != wanted:
        raise ValueError(f"Source products are missing {len(wanted - found)} judged candidates")
    if len(found) != len(selected):
        raise ValueError("Source contains duplicate US product IDs")
    return sorted(selected, key=lambda row: row["product_id"]), judgements


def parquet_rows(location: str, columns: list[str]) -> Iterator[Row]:
    # Preparation-only dependencies; ordinary app startup uses bundled JSONL.
    import fsspec
    import pyarrow.parquet as pq

    with fsspec.open(location, "rb") as source:
        for batch in pq.ParquetFile(source).iter_batches(batch_size=8192, columns=columns):
            yield from batch.to_pylist()


def verify_source_rows(rows: list[Row], canonical: Iterable[Row], name: str) -> None:
    """Do not stamp partial or edited inputs with the pinned source revision."""

    def identities(values: Iterable[Row]) -> Counter[str]:
        return Counter(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in values)

    if identities(rows) != identities(canonical):
        raise ValueError(f"Selected {name} differ from the complete pinned source subset")


def write_jsonl(path: Path, rows: list[Row]) -> None:
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows).encode()
    with (
        path.open("wb") as target,
        gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0) as stream,
    ):
        stream.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--products", required=True, help="Original product Parquet path or HTTPS URL"
    )
    parser.add_argument(
        "--examples", required=True, help="Original example Parquet path or HTTPS URL"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Directory for the rebuilt subset"
    )
    args = parser.parse_args()
    bundled = ROOT / "seed/cameras"
    selection = json.loads((bundled / "query-selection.json").read_text())
    query_ids = {row["query_id"] for row in selection if row["include"]}
    products, judgements = select_records(
        parquet_rows(args.products, PRODUCT_FIELDS),
        parquet_rows(args.examples, JUDGEMENT_FIELDS),
        query_ids,
    )
    for name, rows in (("products", products), ("judgements", judgements)):
        with gzip.open(bundled / f"{name}.jsonl.gz", "rt") as reference:
            verify_source_rows(rows, (json.loads(line) for line in reference), name)
    args.output.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output / "products.jsonl.gz", products)
    write_jsonl(args.output / "judgements.jsonl.gz", judgements)
    for name in ("LICENSE.txt", "NOTICE.txt", "query-selection.json", "examples.json"):
        (args.output / name).write_bytes((bundled / name).read_bytes())
    manifest = {
        "source": "https://github.com/amazon-science/esci-data",
        "source_revision": SOURCE_REVISION,
        "selection": json.loads((bundled / "manifest.json").read_text())["selection"],
        "product_count": len(products),
        "query_count": len(query_ids),
        "judgement_count": len(judgements),
        "missing_description": sum(not row["product_description"] for row in products),
        "missing_bullets": sum(not row["product_bullet_point"] for row in products),
        "checksums": {
            name: hashlib.sha256((args.output / name).read_bytes()).hexdigest()
            for name in (
                "LICENSE.txt",
                "NOTICE.txt",
                "judgements.jsonl.gz",
                "products.jsonl.gz",
                "query-selection.json",
            )
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
