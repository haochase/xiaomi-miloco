# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Owner-scoped, expiring persistence for bounded Outfit recommendation snapshots."""

from __future__ import annotations

import json

from miloco.outfit.recommendation_api import RecommendationSnapshot
from miloco.outfit.storage import OutfitStorage


class RecommendationSnapshotConflictError(ValueError):
    """Raised when one owner reuses a snapshot ID for different persisted facts."""


class RecommendationSnapshotRepository:
    """Persist only bounded recommendation facts under an explicit owner and expiry."""

    def __init__(self, storage: OutfitStorage) -> None:
        self._storage = storage
        self._ensure_schema()

    def save(
        self,
        *,
        owner_person_id: str,
        snapshot: RecommendationSnapshot,
        expires_at_ms: int,
    ) -> None:
        """Atomically persist one snapshot or verify an identical idempotent replay."""

        owner = _require_owner_person_id(owner_person_id)
        expiry = _require_epoch_milliseconds(expires_at_ms)
        if expiry <= snapshot.created_at_ms:
            raise ValueError("expires_at_ms must be after snapshot creation")
        payload_json = _snapshot_payload_json(snapshot)

        with self._storage.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT snapshot_payload_json, expires_at_ms
                FROM outfit_recommendation_snapshots
                WHERE owner_person_id = ? AND snapshot_id = ?
                """,
                (owner, snapshot.snapshot_id),
            ).fetchone()
            if existing is not None:
                if (
                    existing["snapshot_payload_json"] == payload_json
                    and existing["expires_at_ms"] == expiry
                ):
                    return
                raise RecommendationSnapshotConflictError(
                    "recommendation snapshot conflicts with an existing owner snapshot"
                )

            connection.execute(
                """
                INSERT INTO outfit_recommendation_snapshots (
                    owner_person_id,
                    snapshot_id,
                    snapshot_payload_json,
                    created_at_ms,
                    expires_at_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    owner,
                    snapshot.snapshot_id,
                    payload_json,
                    snapshot.created_at_ms,
                    expiry,
                ),
            )

    def get_active(
        self,
        *,
        owner_person_id: str,
        snapshot_id: str,
        now_ms: int,
    ) -> RecommendationSnapshot | None:
        """Return an unexpired snapshot only for its explicitly supplied owner."""

        owner = _require_owner_person_id(owner_person_id)
        now = _require_epoch_milliseconds(now_ms)
        with self._storage.connect() as connection:
            row = connection.execute(
                """
                SELECT snapshot_payload_json
                FROM outfit_recommendation_snapshots
                WHERE owner_person_id = ?
                    AND snapshot_id = ?
                    AND expires_at_ms > ?
                """,
                (owner, snapshot_id, now),
            ).fetchone()
        if row is None:
            return None
        return RecommendationSnapshot.model_validate_json(row["snapshot_payload_json"])

    def purge_expired(self, *, now_ms: int) -> int:
        """Delete every expired snapshot without inspecting or returning its payload."""

        now = _require_epoch_milliseconds(now_ms)
        with self._storage.connect() as connection:
            deleted = connection.execute(
                "DELETE FROM outfit_recommendation_snapshots WHERE expires_at_ms <= ?",
                (now,),
            )
        return deleted.rowcount

    def _ensure_schema(self) -> None:
        with self._storage.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_recommendation_snapshots (
                    owner_person_id TEXT NOT NULL,
                    snapshot_id TEXT NOT NULL,
                    snapshot_payload_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    expires_at_ms INTEGER NOT NULL,
                    PRIMARY KEY (owner_person_id, snapshot_id)
                );

                CREATE INDEX IF NOT EXISTS outfit_recommendation_snapshots_expiry_idx
                ON outfit_recommendation_snapshots (expires_at_ms);
                """
            )


def _snapshot_payload_json(snapshot: RecommendationSnapshot) -> str:
    """Serialize the already bounded DTO without adding owner or media fields."""

    return json.dumps(
        snapshot.model_dump(mode="json"),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _require_owner_person_id(owner_person_id: str) -> str:
    normalized = owner_person_id.strip() if isinstance(owner_person_id, str) else ""
    if not normalized:
        raise ValueError("owner_person_id must not be blank")
    return normalized


def _require_epoch_milliseconds(value: object) -> int:
    """Keep SQLite expiry comparisons finite and independent of coercion rules."""

    if type(value) is not int or value < 0:
        raise ValueError("epoch milliseconds must be a non-negative integer")
    return value
