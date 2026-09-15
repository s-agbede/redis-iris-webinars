"""Validate local reference photographs and join them to explicit product IDs."""

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from app.models import ProductPhoto


class PhotoEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_ids: list[str] = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    photo: ProductPhoto


class PhotoManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photos: list[PhotoEntry]


def load_photos(directory: Path, product_ids: set[str]) -> dict[str, ProductPhoto]:
    """Reject broken assets and ambiguous mappings before serving reference images."""
    manifest = PhotoManifest.model_validate_json((directory / "manifest.json").read_text())
    photos: dict[str, ProductPhoto] = {}
    for entry in manifest.photos:
        path = directory / "assets" / entry.photo.url.removeprefix("/photos/")
        content = path.read_bytes()
        if not content.startswith(b"\xff\xd8\xff"):
            raise ValueError(f"Reference photo is not a JPEG: {path.name}")
        if hashlib.sha256(content).hexdigest() != entry.sha256:
            raise ValueError(f"Reference photo checksum mismatch: {path.name}")
        for product_id in entry.product_ids:
            if product_id not in product_ids:
                raise ValueError(f"Reference photo maps to unknown product: {product_id}")
            if product_id in photos:
                raise ValueError(f"Duplicate reference photo mapping: {product_id}")
            photos[product_id] = entry.photo
    return photos
