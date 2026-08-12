# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Media validation and private storage contracts for Outfit moments."""

from __future__ import annotations

import sqlite3
from io import BytesIO
from pathlib import Path

import pytest
from miloco.life.outfit_media import build_media_asset, validate_media_upload
from miloco.life.outfit_media_repo import OutfitMediaRepo
from miloco.life.outfit_moment_repo import OutfitMomentRepo
from miloco.life.outfit_moments import OutfitMoment
from PIL import Image


def _jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 8), color=(40, 80, 120)).save(output, format="JPEG")
    return output.getvalue()


def _save_moment(repo: OutfitMomentRepo, *, owner_person_id: str = "owner-1") -> None:
    repo.save_or_get(
        OutfitMoment(
            moment_id="moment-1",
            owner_person_id=owner_person_id,
            occurred_at_ms=1_000,
            timezone="Asia/Shanghai",
            recommendation_id="recommendation-1",
            confirmed_wear_event_id="wear-1",
            item_ids=("top-1", "bottom-1", "shoes-1"),
            source_event_ids=("wear-1",),
            created_at_ms=1_001,
        )
    )


@pytest.mark.parametrize("mime", ["image/gif", "image/svg+xml", "text/html"])
def test_media_rejects_unsupported_or_active_content(mime: str) -> None:
    with pytest.raises(ValueError, match="unsupported image type"):
        validate_media_upload(b"not-an-image", mime_type=mime)


def test_media_rejects_invalid_image_bytes() -> None:
    with pytest.raises(ValueError, match="invalid image content"):
        validate_media_upload(b"not-an-image", mime_type="image/jpeg")


def test_media_storage_key_never_uses_client_filename() -> None:
    result = build_media_asset(
        owner_person_id="owner-1",
        moment_id="moment-1",
        content=_jpeg_bytes(),
        mime_type="image/jpeg",
        original_filename="../../secret.jpg",
        source_type="user_upload",
        confirmed_for_history=True,
        created_at_ms=1000,
    )

    assert ".." not in result.asset.storage_key
    assert "secret" not in result.asset.storage_key
    assert result.asset.thumbnail_storage_key is not None
    assert result.thumbnail_content


def test_media_repo_writes_relative_assets_and_deletes_them(tmp_path: Path) -> None:
    database_path = tmp_path / "media.db"
    _save_moment(OutfitMomentRepo(database_path))
    repo = OutfitMediaRepo(database_path, tmp_path / "private-media")
    prepared = build_media_asset(
        owner_person_id="owner-1",
        moment_id="moment-1",
        content=_jpeg_bytes(),
        mime_type="image/jpeg",
        original_filename="outfit.jpg",
        source_type="user_upload",
        confirmed_for_history=True,
        created_at_ms=1000,
    )

    stored = repo.store(prepared)

    assert not Path(stored.storage_key).is_absolute()
    assert repo.read_for_owner(stored.asset_id, "owner-1") == prepared.content
    assert repo.get_for_owner(stored.asset_id, "owner-2") is None
    assert repo.delete_for_owner(stored.asset_id, "owner-1", confirmed=True)
    assert repo.get_for_owner(stored.asset_id, "owner-1") is None
    assert repo.read_for_owner(stored.asset_id, "owner-1") is None


def test_media_repo_requires_explicit_delete_confirmation(tmp_path: Path) -> None:
    database_path = tmp_path / "media.db"
    _save_moment(OutfitMomentRepo(database_path))
    repo = OutfitMediaRepo(database_path, tmp_path / "private-media")
    stored = repo.store(
        build_media_asset(
            owner_person_id="owner-1",
            moment_id="moment-1",
            content=_jpeg_bytes(),
            mime_type="image/jpeg",
            original_filename="outfit.jpg",
            source_type="user_upload",
            confirmed_for_history=True,
            created_at_ms=1000,
        )
    )

    with pytest.raises(ValueError, match="explicit confirmation"):
        repo.delete_for_owner(stored.asset_id, "owner-1", confirmed=False)


def test_media_repo_rejects_assets_without_a_same_owner_moment(tmp_path: Path) -> None:
    database_path = tmp_path / "media.db"
    _save_moment(OutfitMomentRepo(database_path), owner_person_id="owner-1")
    repo = OutfitMediaRepo(database_path, tmp_path / "private-media")
    prepared = build_media_asset(
        owner_person_id="owner-2",
        moment_id="moment-1",
        content=_jpeg_bytes(),
        mime_type="image/jpeg",
        original_filename="outfit.jpg",
        source_type="user_upload",
        confirmed_for_history=True,
        created_at_ms=1_000,
    )

    with pytest.raises(sqlite3.IntegrityError):
        repo.store(prepared)

    assert not list((tmp_path / "private-media").rglob("*"))
