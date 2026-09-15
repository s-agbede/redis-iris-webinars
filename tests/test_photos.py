import hashlib
import json
from pathlib import Path

import pytest

from app.catalog import Catalog
from app.photos import load_photos
from app.settings import ROOT


def test_bundled_photos_match_catalogue_and_exclude_camera_accessories() -> None:
    catalog = Catalog.load(ROOT / "seed/cameras")
    photos = load_photos(ROOT / "seed/photos", set(catalog.products))
    assert photos["B00FOTF8M2"].url == "/photos/nikon-d610.jpg"
    assert photos["B014I11JV0"] == photos["B00FOTF8M2"]
    assert "B07YST2F7Q" not in photos  # An eyecup mentioning D610 is not a camera.
    assert all(photo.caption.startswith("Model reference:") for photo in photos.values())


@pytest.mark.parametrize("problem", ["checksum", "unknown", "duplicate"])
def test_invalid_photo_enrichment_fails_explicitly(tmp_path: Path, problem: str) -> None:
    entry = json.loads((ROOT / "seed/photos/manifest.json").read_text())["photos"][0]
    content = b"\xff\xd8\xfffixture"
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/nikon-d610.jpg").write_bytes(content)
    entry["sha256"] = hashlib.sha256(content).hexdigest()
    entry["product_ids"] = ["a"]
    if problem == "checksum":
        entry["sha256"] = "0" * 64
    elif problem == "unknown":
        entry["product_ids"] = ["absent"]
    else:
        entry["product_ids"] = ["a", "a"]
    (tmp_path / "manifest.json").write_text(json.dumps({"photos": [entry]}))
    with pytest.raises(ValueError, match="checksum|unknown|Duplicate"):
        load_photos(tmp_path, {"a"})
