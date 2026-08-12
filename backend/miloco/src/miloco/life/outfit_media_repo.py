# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Private SQLite metadata and atomic file storage for Outfit media assets."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from miloco.life.outfit_media import OutfitMediaAsset, PreparedOutfitMediaAsset
from miloco.life.outfit_storage import OutfitStorage


class OutfitMediaRepo:
    """Store owner-scoped media metadata and bytes under a dedicated private root."""

    def __init__(self, storage: OutfitStorage | str | Path, storage_root: str | Path):
        self._storage = (
            storage if isinstance(storage, OutfitStorage) else OutfitStorage(storage)
        )
        self._db_path = self._storage.database_path
        self._storage_root = Path(storage_root)
        self._storage_root.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def store(self, prepared: PreparedOutfitMediaAsset) -> OutfitMediaAsset:
        """Atomically materialize server-generated files, then persist metadata."""
        asset = prepared.asset
        written_paths: list[Path] = []
        try:
            content_path = self._storage_path(asset.storage_key)
            self._atomic_write(content_path, prepared.content)
            written_paths.append(content_path)
            if asset.thumbnail_storage_key is not None:
                thumbnail_path = self._storage_path(asset.thumbnail_storage_key)
                self._atomic_write(thumbnail_path, prepared.thumbnail_content)
                written_paths.append(thumbnail_path)
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO outfit_media_asset (
                        asset_id, owner_person_id, moment_id, payload_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        asset.asset_id,
                        asset.owner_person_id,
                        asset.moment_id,
                        asset.model_dump_json(),
                    ),
                )
                conn.commit()
        except Exception:
            for path in written_paths:
                path.unlink(missing_ok=True)
                self._remove_empty_parent_directories(path.parent)
            raise
        return asset

    def get_for_owner(
        self, asset_id: str, owner_person_id: str
    ) -> OutfitMediaAsset | None:
        asset_id = self._require_nonblank(asset_id, "asset_id")
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM outfit_media_asset
                WHERE asset_id = ? AND owner_person_id = ?
                """,
                (asset_id, owner_person_id),
            ).fetchone()
        return (
            None
            if row is None
            else OutfitMediaAsset.model_validate_json(row["payload_json"])
        )

    def read_for_owner(self, asset_id: str, owner_person_id: str) -> bytes | None:
        asset = self.get_for_owner(asset_id, owner_person_id)
        if asset is None:
            return None
        path = self.file_path(asset)
        return None if path is None else path.read_bytes()

    def list_asset_ids_for_moment(
        self, owner_person_id: str, moment_id: str
    ) -> list[str]:
        """Expose only user-confirmed opaque asset ids to the history read model."""
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        moment_id = self._require_nonblank(moment_id, "moment_id")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT asset_id
                FROM outfit_media_asset
                WHERE owner_person_id = ?
                  AND moment_id = ?
                  AND json_extract(payload_json, '$.confirmed_for_history') = 1
                ORDER BY asset_id
                """,
                (owner_person_id, moment_id),
            ).fetchall()
        return [str(row["asset_id"]) for row in rows]

    def file_path(self, asset: OutfitMediaAsset) -> Path | None:
        path = self._storage_path(asset.storage_key)
        return path if path.is_file() else None

    def delete_for_owner(
        self, asset_id: str, owner_person_id: str, *, confirmed: bool
    ) -> bool:
        if not confirmed:
            raise ValueError("media deletion requires explicit confirmation")
        asset = self.get_for_owner(asset_id, owner_person_id)
        if asset is None:
            return False
        with self._connect() as conn:
            conn.execute(
                """
                DELETE FROM outfit_media_asset
                WHERE asset_id = ? AND owner_person_id = ?
                """,
                (asset.asset_id, asset.owner_person_id),
            )
            conn.commit()
        self._storage_path(asset.storage_key).unlink(missing_ok=True)
        if asset.thumbnail_storage_key is not None:
            self._storage_path(asset.thumbnail_storage_key).unlink(missing_ok=True)
        return True

    def _atomic_write(self, target: Path, content: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise ValueError("refusing to overwrite an existing media file")
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _storage_path(self, storage_key: str) -> Path:
        candidate = (self._storage_root / storage_key).resolve()
        root = self._storage_root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("storage key escapes Outfit private media root")
        return candidate

    def _remove_empty_parent_directories(self, directory: Path) -> None:
        root = self._storage_root.resolve()
        while directory != root:
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent

    def _connect(self):
        return self._storage.connect()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_media_asset (
                    owner_person_id TEXT NOT NULL,
                    asset_id TEXT NOT NULL,
                    moment_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, asset_id),
                    FOREIGN KEY (owner_person_id, moment_id)
                        REFERENCES outfit_moment(owner_person_id, moment_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_outfit_media_asset_owner_moment
                ON outfit_media_asset(owner_person_id, moment_id);
                """
            )
            conn.commit()

    @staticmethod
    def _require_nonblank(value: str, field_name: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must not be blank")
        return value
