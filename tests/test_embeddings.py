import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from app.embeddings import LocalEncoder, resolve_model
from app.settings import Settings


def test_model_preparation_reuses_verified_cache_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app import embeddings

    (tmp_path / "seed").mkdir()
    (tmp_path / "model.onnx").write_bytes(b"model")
    (tmp_path / "seed/local-model.json").write_text(
        json.dumps({"checksums": {"model.onnx": hashlib.sha256(b"model").hexdigest()}})
    )
    monkeypatch.setattr(embeddings, "ROOT", tmp_path)
    calls: list[bool] = []

    def snapshot(**kwargs: object) -> str:
        calls.append(bool(kwargs["local_files_only"]))
        return str(tmp_path)

    monkeypatch.setattr(embeddings, "snapshot_download", snapshot)
    assert resolve_model(Settings(_env_file=None), download=True) == tmp_path
    assert calls == [True]


def test_missing_local_model_has_an_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="make model"):
        resolve_model(Settings(_env_file=None, model_path=tmp_path))


def test_mean_pooling_ignores_padding_and_normalizes() -> None:
    hidden = np.array([[[3.0, 0.0], [0.0, 4.0], [99.0, 99.0]]], dtype=np.float32)
    mask = np.array([[1, 1, 0]])
    pooled = LocalEncoder.pool(hidden, mask)
    assert pooled[0] == pytest.approx([0.6, 0.8])


def test_real_model_rejects_overlong_inputs_without_silent_truncation() -> None:
    try:
        path = resolve_model(Settings(_env_file=None))
    except RuntimeError:
        pytest.skip("Run make model for the real local-model checks.")
    encoder = LocalEncoder(path)
    with pytest.raises(ValueError, match="256"):
        encoder.embed("photography " * 300)
    vector = encoder.embed("a camera lens")
    assert len(vector) == 384
    assert np.linalg.norm(vector) == pytest.approx(1.0, abs=1e-5)
