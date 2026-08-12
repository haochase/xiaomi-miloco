# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Append-only SQLite persistence for Outfit feedback facts."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from miloco.life.outfit_feedback_events import OutfitFeedbackEvent


class OutfitFeedbackEventConflictError(ValueError):
    """Raised when a replay changes an immutable Outfit feedback event."""


class OutfitFeedbackEventRepo:
    """Persist immutable feedback events and expose owner-scoped reads."""

    def __init__(self, db_path: str | Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def append(self, event: OutfitFeedbackEvent) -> OutfitFeedbackEvent:
        """Append a fact once or return an exact owner-scoped replay."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO outfit_feedback_event (
                        event_id, owner_person_id, occurred_at_ms, payload_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.owner_person_id,
                        event.occurred_at_ms,
                        event.model_dump_json(),
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError as error:
            stored = self.get_for_owner(event.event_id, event.owner_person_id)
            if stored is None:
                raise error
            if stored == event:
                return stored
            raise OutfitFeedbackEventConflictError(
                "existing Outfit feedback event differs from replay inputs"
            ) from error
        return event

    def get_for_owner(
        self, event_id: str, owner_person_id: str
    ) -> OutfitFeedbackEvent | None:
        event_id = self._require_nonblank(event_id, "event_id")
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM outfit_feedback_event
                WHERE event_id = ? AND owner_person_id = ?
                """,
                (event_id, owner_person_id),
            ).fetchone()
        return (
            None
            if row is None
            else OutfitFeedbackEvent.model_validate_json(row["payload_json"])
        )

    def list_for_owner(self, owner_person_id: str) -> list[OutfitFeedbackEvent]:
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json
                FROM outfit_feedback_event
                WHERE owner_person_id = ?
                ORDER BY occurred_at_ms, rowid
                """,
                (owner_person_id,),
            ).fetchall()
        return [
            OutfitFeedbackEvent.model_validate_json(row["payload_json"]) for row in rows
        ]

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_feedback_event (
                    owner_person_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    occurred_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_outfit_feedback_event_owner_time
                ON outfit_feedback_event(owner_person_id, occurred_at_ms);
                """
            )
            conn.commit()

    @staticmethod
    def _require_nonblank(value: str, field_name: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must not be blank")
        return value
