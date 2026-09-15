"""Exploratory retrieval comparison; no application dependencies or services are changed."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import onnxruntime as ort
import pyarrow.parquet as pq
import snowballstemmer
import yaml
from rank_bm25 import BM25Okapi
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parents[1] / "data"
MODEL = Path(os.environ["SEARCH_PILOT_MODEL_PATH"])
STOPWORDS = set(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "being",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "should",
        "so",
        "that",
        "the",
        "their",
        "them",
        "there",
        "these",
        "they",
        "this",
        "to",
        "was",
        "we",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
        "you",
        "your",
    ]
)
STEMMER = snowballstemmer.stemmer("english")

KUBERNETES_QUERIES = [
    ("identifier-crash", "CrashLoopBackOff"),
    ("identifier-image", "ImagePullBackOff"),
    ("identifier-disruption", "PodDisruptionBudget"),
    ("identifier-logs", "kubectl logs --previous"),
    ("intent-logs", "How do I see what my program printed before it died?"),
    ("intent-ready", "Stop sending customers to my application until it has finished starting"),
    ("intent-disruption", "Keep two copies of my app available while machines are being serviced"),
    ("intent-secret", "Let an app read a password without storing it in its image"),
    ("mixed-ready", "readinessProbe stop traffic while the application warms up"),
    ("mixed-logs", "kubectl logs output from the previous crashed container"),
    ("mixed-disruption", "PodDisruptionBudget keep replicas available during node maintenance"),
    ("mixed-pull", "ImagePullBackOff private registry credentials"),
]


def clean_text(value: str | None) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def documents(dataset: str) -> list[dict[str, Any]]:
    if dataset == "esci":
        products = pq.read_table(ROOT / "esci_audio_products.parquet").to_pylist()
        return [
            {
                "id": row["product_id"],
                "title": clean_text(row["product_title"]),
                "text": clean_text(
                    " ".join(
                        row[field] or ""
                        for field in [
                            "product_brand",
                            "product_color",
                            "product_description",
                            "product_bullet_point",
                        ]
                    )
                ),
                "source_fields": row,
            }
            for row in products
        ]
    result = []
    for entry in json.loads((ROOT / "kubernetes_manifest.json").read_text()):
        raw = (ROOT / "kubernetes_raw" / entry["local_name"]).read_text()
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, flags=re.S)
        metadata = yaml.safe_load(match.group(1)) if match else {}
        title = str(metadata.get("title", entry["path"]))
        body = raw[match.end() :] if match else raw
        body = re.sub(r"\{\{.*?\}\}", " ", body, flags=re.S)
        body = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", body)
        body = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", body)
        body = re.sub(r"https?://\S+", " ", body)
        body = clean_text(body)
        if len(body) < 200:
            continue
        result.append(
            {
                "id": entry["path"].removeprefix("content/en/docs/"),
                "title": title,
                "text": body,
                "url": entry["url"],
            }
        )
    return result


def lexical_tokens(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", text.lower())
    return STEMMER.stemWords([token for token in tokens if token not in STOPWORDS])


class Encoder:
    def __init__(self) -> None:
        self.tokenizer = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(MODEL / "onnx/model.onnx"), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def encode(self, texts: list[str], report: bool = False) -> np.ndarray:
        vectors = []
        start = perf_counter()
        for offset in range(0, len(texts), 32):
            encoded = self.tokenizer.encode_batch(texts[offset : offset + 32])
            masks = np.asarray([x.attention_mask for x in encoded], dtype=np.int64)
            inputs = {
                "input_ids": np.asarray([x.ids for x in encoded], dtype=np.int64),
                "attention_mask": masks,
                "token_type_ids": np.asarray([x.type_ids for x in encoded], dtype=np.int64),
            }
            outputs = self.session.run(None, inputs)[0]
            mean = (outputs * masks[:, :, None]).sum(axis=1) / masks.sum(axis=1)[:, None]
            vectors.append((mean / np.linalg.norm(mean, axis=1, keepdims=True)).astype(np.float32))
            if report and offset % 640 == 0:
                print(
                    f"Embedded {min(offset + 32, len(texts))}/{len(texts)} chunks "
                    f"in {perf_counter() - start:.1f}s",
                    flush=True,
                )
        return np.concatenate(vectors)


def make_chunks(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokenizer = Tokenizer.from_file(str(MODEL / "tokenizer.json"))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    chunks = []
    for index, doc in enumerate(docs):
        title_ids = tokenizer.encode(doc["title"], add_special_tokens=False).ids[:48]
        title = tokenizer.decode(title_ids)
        body_ids = tokenizer.encode(doc["text"], add_special_tokens=False).ids
        window = 250 - len(title_ids)
        stride = window - 40
        for offset in range(0, max(len(body_ids), 1), stride):
            body = tokenizer.decode(body_ids[offset : offset + window])
            chunks.append({"doc_index": index, "text": f"{title}. {body}"})
            if offset + window >= len(body_ids):
                break
    return chunks


def main(dataset: str) -> None:
    output = ROOT / dataset
    output.mkdir(exist_ok=True)
    docs = documents(dataset)
    chunks = make_chunks(docs)
    print(dataset, len(docs), "documents", len(chunks), "chunks", flush=True)
    (output / "documents.json").write_text(json.dumps(docs, indent=2))
    (output / "chunks.json").write_text(json.dumps(chunks))
    encoder = Encoder()
    path = output / "embeddings-full-chunks.npy"
    if path.exists():
        embeddings = np.load(path)
        assert len(embeddings) == len(chunks)
    else:
        embeddings = encoder.encode([chunk["text"] for chunk in chunks], report=True)
        np.save(path, embeddings)
    assert np.isfinite(embeddings).all()
    assert np.allclose(np.linalg.norm(embeddings, axis=1), 1, atol=1e-5)
    chunk_doc_indices = np.array([chunk["doc_index"] for chunk in chunks])
    bm25 = BM25Okapi([lexical_tokens(chunk["text"]) for chunk in chunks], k1=1.5, b=0.75)
    if dataset == "kubernetes":
        queries = [
            {"id": key, "query": text, "origin": "authored before retrieval"}
            for key, text in KUBERNETES_QUERIES
        ]
    else:
        rows = pq.read_table(ROOT / "esci_audio_examples.parquet").to_pylist()
        dedup = {
            row["query_id"]: {
                "id": str(row["query_id"]),
                "query": row["query"],
                "origin": "ESCI",
                "split": row["split"],
            }
            for row in rows
        }
        queries = list(dedup.values())
    labels = (
        {(str(row["query_id"]), row["product_id"]): row["esci_label"] for row in rows}
        if dataset == "esci"
        else {}
    )
    (output / "queries.json").write_text(json.dumps(queries, indent=2))
    query_vectors = encoder.encode([q["query"] for q in queries])
    np.save(output / "query-vectors.npy", query_vectors)
    rows = []
    for query, q_vector in zip(queries, query_vectors, strict=True):
        lexical = bm25.get_scores(lexical_tokens(query["query"]))
        semantic = embeddings @ q_vector
        lexical_docs = np.zeros(len(docs))
        semantic_docs = np.full(len(docs), -np.inf)
        np.maximum.at(lexical_docs, chunk_doc_indices, lexical)
        np.maximum.at(semantic_docs, chunk_doc_indices, semantic)
        lex_order = np.argsort(-lexical_docs, kind="stable")
        lex_order = lex_order[lexical_docs[lex_order] > 0]
        vec_order = np.argsort(-semantic_docs, kind="stable")
        fusion = np.zeros(len(docs))
        for order in [lex_order[:50], vec_order[:50]]:
            for rank, doc_index in enumerate(order, 1):
                fusion[doc_index] += 1 / (60 + rank)
        hybrid_order = np.argsort(-fusion, kind="stable")[:50]
        result: dict[str, Any] = dict(query)
        for name, order, scores in [
            ("text", lex_order, lexical_docs),
            ("vector", vec_order, semantic_docs),
            ("hybrid", hybrid_order, fusion),
        ]:
            result[name] = [
                {
                    "id": docs[i]["id"],
                    "title": docs[i]["title"],
                    "score": float(scores[i]),
                    "esci_label": labels.get((query["id"], docs[i]["id"]), "unjudged"),
                }
                for i in order[:10]
            ]
        rows.append(result)
    (output / "results.json").write_text(json.dumps(rows, indent=2))
    print("Saved", output / "results.json", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["esci", "kubernetes"])
    main(parser.parse_args().dataset)
