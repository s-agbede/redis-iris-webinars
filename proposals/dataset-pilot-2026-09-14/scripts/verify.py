"""Check source integrity, recorded results and the pilot's text-coverage regression."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def main() -> None:
    evidence = json.loads((ROOT / "evidence.json").read_text())
    products = pq.read_table(DATA / "esci_audio_products.parquet").to_pylist()
    examples = pq.read_table(DATA / "esci_audio_examples.parquet").to_pylist()
    product_ids = {row["product_id"] for row in products}
    assert len(product_ids) == len(products) == evidence["counts"]["esci_products"]
    assert all(row["product_locale"] == "us" for row in products)
    assert product_ids == {row["product_id"] for row in examples}
    assert len(examples) == evidence["counts"]["esci_judgements"]
    assert len({row["query_id"] for row in examples}) == evidence["counts"]["esci_queries"]
    for conflict in evidence["label_conflicts"]:
        matching = [
            row
            for row in examples
            if str(row["query_id"]) == conflict["query_id"]
            and row["product_id"] == conflict["product_id"]
        ]
        assert matching and matching[0]["esci_label"] == conflict["source_label"]
    print("ESCI source joins, counts and retained label conflicts: passed")

    manifest = json.loads((DATA / "kubernetes_manifest.json").read_text())
    assert len(manifest) == evidence["counts"]["kubernetes_source_pages"]
    for page in manifest:
        raw = (DATA / "kubernetes_raw" / page["local_name"]).read_bytes()
        header = f"blob {len(raw)}\0".encode()
        assert hashlib.sha1(header + raw).hexdigest() == page["sha"], page["path"]
    print("All 166 Kubernetes source files match their pinned Git blob hashes")

    for dataset in ["esci", "kubernetes"]:
        results = json.loads((DATA / dataset / "results.json").read_text())
        queries = json.loads((DATA / dataset / "queries.json").read_text())
        assert len(results) == len(queries) == evidence["counts"][f"{dataset}_queries"]
        assert {row["id"] for row in queries} == {row["id"] for row in results}
        for row in results:
            for mode in ["text", "vector", "hybrid"]:
                ids = [hit["id"] for hit in row[mode]]
                assert len(ids) == len(set(ids))
                assert np.isfinite([hit["score"] for hit in row[mode]]).all()
                if dataset == "esci":
                    assert set(ids) <= product_ids
        selected_key = (
            "selected_esci_search_cases"
            if dataset == "esci"
            else "selected_kubernetes_search_cases"
        )
        by_id = {row["id"]: row for row in results}
        assert all(row == by_id[row["id"]] for row in evidence[selected_key])
    print("All 456 query outputs and selected report cases: passed")

    assert len(list((ROOT / "licenses").glob("*.txt"))) == 3
    if "SEARCH_PILOT_MODEL_PATH" in os.environ:
        from compare import Encoder, documents, make_chunks

        chunks = make_chunks(
            [
                {
                    "id": "long",
                    "title": "Long document",
                    "text": ("ordinary text " * 400) + "unique final zebra",
                }
            ]
        )
        assert len(chunks) > 1 and "unique final zebra" in chunks[-1]["text"]
        for dataset in ["esci", "kubernetes"]:
            docs = documents(dataset)
            assert len(make_chunks(docs)) == evidence["counts"][f"{dataset}_chunks"]
        encoder = Encoder()
        for dataset in ["esci", "kubernetes"]:
            pairs = json.loads((DATA / dataset / "cache-pairs.json").read_text())
            for pair in pairs:
                texts = (
                    [pair["query_a"], pair["query_b"]]
                    if dataset == "esci"
                    else [pair["a"], pair["b"]]
                )
                vectors = encoder.encode(texts)
                assert np.isclose(float(vectors[0] @ vectors[1]), pair["cosine"], atol=1e-5)
        print("Long-document coverage, chunk counts and recomputed cache similarities: passed")
    else:
        print("Model checks skipped: set SEARCH_PILOT_MODEL_PATH to run them")


if __name__ == "__main__":
    main()
