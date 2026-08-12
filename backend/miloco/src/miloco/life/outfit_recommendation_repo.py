# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Private persistence for immutable Outfit recommendation snapshots."""

from __future__ import annotations

from pathlib import Path

from miloco.life.outfit_recommendations import OutfitRecommendationSnapshot
from miloco.life.outfit_storage import OutfitStorage


class OutfitRecommendationRepo:
    """Store snapshots by configured owner for later explicit wear confirmation."""

    def __init__(self, storage: OutfitStorage | str | Path):
        self._storage = (
            storage if isinstance(storage, OutfitStorage) else OutfitStorage(storage)
        )
        self._init_schema()

    def save_or_get(
        self,
        snapshot: OutfitRecommendationSnapshot,
    ) -> OutfitRecommendationSnapshot:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO outfit_recommendation_snapshot (
                    owner_person_id, recommendation_id, created_at_ms, payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    snapshot.owner_person_id,
                    snapshot.recommendation_id,
                    snapshot.created_at_ms,
                    snapshot.model_dump_json(),
                ),
            )
            row = conn.execute(
                """
                SELECT payload_json FROM outfit_recommendation_snapshot
                WHERE owner_person_id = ? AND recommendation_id = ?
                """,
                (snapshot.owner_person_id, snapshot.recommendation_id),
            ).fetchone()
        return OutfitRecommendationSnapshot.model_validate_json(row["payload_json"])

    def get_for_owner(
        self,
        owner_person_id: str,
        recommendation_id: str,
    ) -> OutfitRecommendationSnapshot | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM outfit_recommendation_snapshot
                WHERE owner_person_id = ? AND recommendation_id = ?
                """,
                (owner_person_id, recommendation_id),
            ).fetchone()
        return (
            OutfitRecommendationSnapshot.model_validate_json(row["payload_json"])
            if row is not None
            else None
        )

    def _connect(self):
        return self._storage.connect()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_recommendation_snapshot (
                    owner_person_id TEXT NOT NULL,
                    recommendation_id TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, recommendation_id)
                );

                CREATE INDEX IF NOT EXISTS idx_outfit_recommendation_owner_time
                ON outfit_recommendation_snapshot(owner_person_id, created_at_ms);
                """
            )
