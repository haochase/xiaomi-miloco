# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Safe image preparation and immutable metadata for Outfit moment media."""

from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from typing import Literal
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, model_validator

ALLOWED_IMAGE_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
THUMBNAIL_SIZE = (640, 640)

_MIME_TO_FORMAT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
_MIME_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

OutfitMediaSourceType = Literal["try_on_capture", "user_upload"]


@dataclass(frozen=True)
class ValidatedMediaUpload:
    """Re-encoded content and thumbnail after decoding untrusted image bytes."""

    content: bytes
    thumbnail_content: bytes
    mime_type: str


class OutfitMediaAsset(BaseModel):
    """Private media metadata; storage keys are never returned as public API data."""

    model_config = ConfigDict(frozen=True)

    asset_id: str
    owner_person_id: str
    moment_id: str
    source_type: OutfitMediaSourceType
    storage_key: str
    thumbnail_storage_key: str | None = None
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    size_bytes: int = Field(gt=0, le=MAX_IMAGE_BYTES)
    sha256: str
    captured_at_ms: int | None = Field(default=None, ge=0)
    confirmed_for_history: bool
    created_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _validate_private_metadata(self) -> "OutfitMediaAsset":
        if not self.asset_id.strip() or not self.owner_person_id.strip():
            raise ValueError("asset and owner ids must not be blank")
        if not self.moment_id.strip():
            raise ValueError("moment id must not be blank")
        _validate_relative_storage_key(self.storage_key)
        if self.thumbnail_storage_key is not None:
            _validate_relative_storage_key(self.thumbnail_storage_key)
        if len(self.sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("sha256 must be a lowercase hexadecimal digest")
        return self


@dataclass(frozen=True)
class PreparedOutfitMediaAsset:
    """An asset plus the server-generated image bytes that must be stored together."""

    asset: OutfitMediaAsset
    content: bytes
    thumbnail_content: bytes


def validate_media_upload(content: bytes, *, mime_type: str) -> ValidatedMediaUpload:
    """Decode and re-encode a supported image before it reaches private storage."""
    mime_type = mime_type.strip().lower()
    if mime_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValueError("unsupported image type")
    if not content:
        raise ValueError("image content must not be empty")
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("image exceeds maximum size")

    expected_format = _MIME_TO_FORMAT[mime_type]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as opened:
                opened.load()
                if opened.format != expected_format:
                    raise ValueError("image content does not match mime type")
                if opened.width * opened.height > MAX_IMAGE_PIXELS:
                    raise ValueError("image exceeds maximum pixel count")
                image = opened.copy()
    except ValueError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        UnidentifiedImageError,
    ) as error:
        raise ValueError("invalid image content") from error

    normalized_content = _encode_image(image, expected_format)
    thumbnail = image.copy()
    thumbnail.thumbnail(THUMBNAIL_SIZE)
    thumbnail_content = _encode_image(thumbnail.convert("RGB"), "JPEG")
    return ValidatedMediaUpload(
        content=normalized_content,
        thumbnail_content=thumbnail_content,
        mime_type=mime_type,
    )


def build_media_asset(
    *,
    owner_person_id: str,
    moment_id: str,
    content: bytes,
    mime_type: str,
    original_filename: str | None,
    source_type: OutfitMediaSourceType,
    confirmed_for_history: bool,
    created_at_ms: int,
    captured_at_ms: int | None = None,
) -> PreparedOutfitMediaAsset:
    """Build opaque private keys without trusting caller-controlled file names."""
    owner_person_id = _require_nonblank(owner_person_id, "owner_person_id")
    moment_id = _require_nonblank(moment_id, "moment_id")
    _ = original_filename
    validated = validate_media_upload(content, mime_type=mime_type)
    asset_id = f"asset-{uuid4().hex}"
    scope = hashlib.sha256(
        f"{owner_person_id}\x00{moment_id}".encode("utf-8")
    ).hexdigest()[:16]
    extension = _MIME_TO_EXTENSION[validated.mime_type]
    storage_key = f"{scope}/assets/{asset_id}.{extension}"
    thumbnail_storage_key = f"{scope}/thumbnails/{asset_id}.jpg"
    asset = OutfitMediaAsset(
        asset_id=asset_id,
        owner_person_id=owner_person_id,
        moment_id=moment_id,
        source_type=source_type,
        storage_key=storage_key,
        thumbnail_storage_key=thumbnail_storage_key,
        mime_type=validated.mime_type,
        size_bytes=len(validated.content),
        sha256=hashlib.sha256(validated.content).hexdigest(),
        captured_at_ms=captured_at_ms,
        confirmed_for_history=confirmed_for_history,
        created_at_ms=created_at_ms,
    )
    return PreparedOutfitMediaAsset(
        asset=asset,
        content=validated.content,
        thumbnail_content=validated.thumbnail_content,
    )


def _encode_image(image: Image.Image, image_format: str) -> bytes:
    output = BytesIO()
    save_image = image.convert("RGB") if image_format == "JPEG" else image
    save_image.save(output, format=image_format)
    return output.getvalue()


def _validate_relative_storage_key(storage_key: str) -> None:
    if not storage_key or "\\" in storage_key:
        raise ValueError("storage key must be a safe relative path")
    path = PurePosixPath(storage_key)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("storage key must be a safe relative path")


def _require_nonblank(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be blank")
    return value
