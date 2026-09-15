"""Pinned MiniLM ONNX embeddings, normalized exactly as the source model specifies."""

import hashlib
import json
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
from huggingface_hub import snapshot_download
from tokenizers import Tokenizer

from app.settings import ROOT, Settings, get_settings


def resolve_model(settings: Settings, *, download: bool = False) -> Path:
    """Only the explicit model preparation command is allowed to use the network."""
    manifest = json.loads((ROOT / "seed/local-model.json").read_text())

    def verified_path(*, local_only: bool) -> Path:
        directory = settings.model_path or Path(
            snapshot_download(
                repo_id=settings.embedding_model,
                revision=settings.embedding_revision,
                allow_patterns=list(manifest["checksums"]),
                local_files_only=local_only,
                force_download=not local_only,
            )
        )
        for name, expected in manifest["checksums"].items():
            if hashlib.sha256((directory / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Unexpected model file: {name}")
        return directory

    try:
        try:
            return verified_path(local_only=True)
        except (OSError, ValueError):
            if not download or settings.model_path:
                raise
            return verified_path(local_only=False)
    except (OSError, ValueError) as exc:
        raise RuntimeError(
            "Local model is missing or differs from the pinned revision. Run make model."
        ) from exc


class LocalEncoder:
    """Small CPU runtime; a separate unpadded tokenizer also supplies source offsets."""

    def __init__(self, directory: Path) -> None:
        import onnxruntime as ort

        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.no_padding()
        self.tokenizer.no_truncation()
        self._inference_tokenizer = Tokenizer.from_str(self.tokenizer.to_str())
        self._inference_tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(directory / "onnx/model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._inputs = {value.name for value in self._session.get_inputs()}

    @staticmethod
    def pool(
        hidden: npt.NDArray[np.float32], mask: npt.NDArray[np.int64]
    ) -> npt.NDArray[np.float32]:
        weights = mask[..., None].astype(np.float32)
        mean = (hidden * weights).sum(axis=1) / weights.sum(axis=1).clip(min=1)
        result = mean / np.linalg.norm(mean, axis=1, keepdims=True).clip(min=1e-12)
        return cast(npt.NDArray[np.float32], result.astype(np.float32))

    def embed_many(self, texts: list[str], batch_size: int = 32) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = self._inference_tokenizer.encode_batch(texts[start : start + batch_size])
            if any(len(row.ids) > 256 for row in batch):
                raise ValueError("The local model accepts at most 256 tokens; shorten this query.")
            inputs = {
                "input_ids": np.array([row.ids for row in batch], dtype=np.int64),
                "attention_mask": np.array([row.attention_mask for row in batch], dtype=np.int64),
                "token_type_ids": np.array([row.type_ids for row in batch], dtype=np.int64),
            }
            output = self._session.run(None, {k: v for k, v in inputs.items() if k in self._inputs})
            hidden = cast(npt.NDArray[np.float32], output[0])
            vectors.extend(self.pool(hidden, inputs["attention_mask"]).tolist())
        return vectors

    def embed(self, text: str) -> list[float]:
        return self.embed_many([text])[0]


def build_vectorizer(settings: Settings) -> LocalEncoder:
    return LocalEncoder(resolve_model(settings))


if __name__ == "__main__":
    location = resolve_model(get_settings(), download=True)
    print(f"Local model verified: {location}\nServing and seeding can now run offline.")
