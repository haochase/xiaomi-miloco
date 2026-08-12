# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Owner-scoped SQLite storage for immutable Outfit moment projections."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from miloco.life.outfit_moments import OutfitMoment, OutfitMomentTag
from miloco.life.outfit_storage import OutfitStorage


class OutfitMomentProjectionConflictError(ValueError):
    """Raised when a projection retry changes immutable input facts."""


class OutfitMomentRepo:
    """Persist one stable Outfit moment projection for each confirmed wear event."""

    def __init__(self, storage: OutfitStorage | str | Path):
        self._storage = (
            storage if isinstance(storage, OutfitStorage) else OutfitStorage(storage)
        )
        self._db_path = self._storage.database_path
        self._init_schema()

    def save_or_get(self, moment: OutfitMoment) -> OutfitMoment:
        """Insert a projection once or return an exact persisted replay.

        A retry can occur after the original writer committed but before the
        caller received its response. Only the retry-local projection creation
        timestamp may differ in that case.
        """
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO outfit_moment (
                        owner_person_id,
                        moment_id,
                        occurred_at_ms,
                        confirmed_wear_event_id,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        moment.owner_person_id,
                        moment.moment_id,
                        moment.occurred_at_ms,
                        moment.confirmed_wear_event_id,
                        moment.model_dump_json(),
                    ),
                )
                conn.commit()
        except sqlite3.IntegrityError as error:
            stored = self._find_existing_projection(moment)
            if stored is None:
                raise error
            if self._same_projection_inputs(stored, moment):
                return stored
            raise OutfitMomentProjectionConflictError(
                "existing Outfit moment projection differs from retry inputs"
            ) from error
        return moment

    def get_for_owner(
        self, owner_person_id: str, moment_id: str
    ) -> OutfitMoment | None:
        """Return a moment only when it belongs to the requested owner."""
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        moment_id = self._require_nonblank(moment_id, "moment_id")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM outfit_moment
                WHERE owner_person_id = ? AND moment_id = ?
                """,
                (owner_person_id, moment_id),
            ).fetchone()
        return (
            None
            if row is None
            else OutfitMoment.model_validate_json(row["payload_json"])
        )

    def list_for_owner(
        self, owner_person_id: str, *, limit: int = 10, since_ms: int | None = None
    ) -> list[OutfitMoment]:
        """List one owner's newest projections, optionally from a time boundary."""
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        if since_ms is not None and (
            not isinstance(since_ms, int) or isinstance(since_ms, bool) or since_ms < 0
        ):
            raise ValueError("since_ms must be a non-negative integer")

        where = "owner_person_id = ?"
        params: list[object] = [owner_person_id]
        if since_ms is not None:
            where += " AND occurred_at_ms >= ?"
            params.append(since_ms)
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT payload_json
                FROM outfit_moment
                WHERE {where}
                ORDER BY occurred_at_ms DESC, moment_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [OutfitMoment.model_validate_json(row["payload_json"]) for row in rows]

    def list_tags_for_owner(
        self,
        owner_person_id: str,
        moment_id: str,
        *,
        include_rejected: bool = False,
    ) -> list[OutfitMomentTag]:
        """Return reviewable tags without leaking tags across owner boundaries."""
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        moment_id = self._require_nonblank(moment_id, "moment_id")
        where = "owner_person_id = ? AND moment_id = ?"
        params: list[object] = [owner_person_id, moment_id]
        if not include_rejected:
            where += " AND review_status != 'rejected'"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT payload_json
                FROM outfit_moment_tag
                WHERE {where}
                ORDER BY tag_id
                """,
                params,
            ).fetchall()
        return [
            OutfitMomentTag.model_validate_json(row["payload_json"]) for row in rows
        ]

    def store_candidate_tags(
        self,
        owner_person_id: str,
        moment_id: str,
        candidates: list[OutfitMomentTag],
    ) -> list[OutfitMomentTag]:
        """Insert only new candidate keys and preserve every user review decision."""
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        moment_id = self._require_nonblank(moment_id, "moment_id")
        if any(tag.moment_id != moment_id for tag in candidates):
            raise ValueError("candidate tag moment ids must match the requested moment")
        with self._connect() as conn:
            for tag in candidates:
                existing = conn.execute(
                    """
                    SELECT 1
                    FROM outfit_moment_tag
                    WHERE owner_person_id = ? AND dedupe_key = ?
                    """,
                    (owner_person_id, tag.dedupe_key),
                ).fetchone()
                if existing is not None:
                    continue
                conn.execute(
                    """
                    INSERT INTO outfit_moment_tag (
                        owner_person_id,
                        moment_id,
                        tag_id,
                        dedupe_key,
                        review_status,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        owner_person_id,
                        moment_id,
                        tag.tag_id,
                        tag.dedupe_key,
                        tag.review_status,
                        tag.model_dump_json(),
                    ),
                )
            conn.commit()
        return self.list_tags_for_owner(owner_person_id, moment_id)

    def get_tag_for_owner(
        self, owner_person_id: str, tag_id: str
    ) -> OutfitMomentTag | None:
        owner_person_id = self._require_nonblank(owner_person_id, "owner_person_id")
        tag_id = self._require_nonblank(tag_id, "tag_id")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM outfit_moment_tag
                WHERE owner_person_id = ? AND tag_id = ?
                """,
                (owner_person_id, tag_id),
            ).fetchone()
        return (
            None
            if row is None
            else OutfitMomentTag.model_validate_json(row["payload_json"])
        )

    def update_tag_for_owner(
        self,
        owner_person_id: str,
        tag_id: str,
        *,
        review_status: str,
        label: str | None = None,
        narrative: str | None = None,
    ) -> OutfitMomentTag | None:
        """Persist an explicit review action; client evidence never enters this path."""
        current = self.get_tag_for_owner(owner_person_id, tag_id)
        if current is None:
            return None
        payload = current.model_dump()
        payload["review_status"] = review_status
        if label is not None:
            payload["label"] = label
        if narrative is not None:
            payload["narrative"] = narrative
        updated = OutfitMomentTag.model_validate(payload)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE outfit_moment_tag
                SET review_status = ?, payload_json = ?
                WHERE owner_person_id = ? AND tag_id = ?
                """,
                (
                    updated.review_status,
                    updated.model_dump_json(),
                    owner_person_id,
                    tag_id,
                ),
            )
            conn.commit()
        return updated

    def _find_existing_projection(self, moment: OutfitMoment) -> OutfitMoment | None:
        by_wear_event = self._get_by_confirmed_wear_event(
            moment.owner_person_id, moment.confirmed_wear_event_id
        )
        by_moment_id = self.get_for_owner(moment.owner_person_id, moment.moment_id)
        if (
            by_wear_event is not None
            and by_moment_id is not None
            and by_wear_event != by_moment_id
        ):
            raise OutfitMomentProjectionConflictError(
                "moment id and confirmed wear event identify different projections"
            )
        return by_wear_event or by_moment_id

    def _get_by_confirmed_wear_event(
        self, owner_person_id: str, confirmed_wear_event_id: str
    ) -> OutfitMoment | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM outfit_moment
                WHERE owner_person_id = ? AND confirmed_wear_event_id = ?
                """,
                (owner_person_id, confirmed_wear_event_id),
            ).fetchone()
        return (
            None
            if row is None
            else OutfitMoment.model_validate_json(row["payload_json"])
        )

    @staticmethod
    def _same_projection_inputs(stored: OutfitMoment, attempted: OutfitMoment) -> bool:
        return stored.model_dump(exclude={"created_at_ms"}) == attempted.model_dump(
            exclude={"created_at_ms"}
        )

    def _connect(self):
        return self._storage.connect()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_moment (
                    owner_person_id TEXT NOT NULL,
                    moment_id TEXT NOT NULL,
                    occurred_at_ms INTEGER NOT NULL,
                    confirmed_wear_event_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, moment_id),
                    UNIQUE (owner_person_id, confirmed_wear_event_id)
                );

                CREATE INDEX IF NOT EXISTS idx_outfit_moment_owner_time
                ON outfit_moment(owner_person_id, occurred_at_ms DESC);

                CREATE TABLE IF NOT EXISTS outfit_moment_tag (
                    owner_person_id TEXT NOT NULL,
                    moment_id TEXT NOT NULL,
                    tag_id TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL,
                    review_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, tag_id),
                    UNIQUE (owner_person_id, dedupe_key),
                    FOREIGN KEY (owner_person_id, moment_id)
                        REFERENCES outfit_moment(owner_person_id, moment_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_outfit_moment_tag_owner_moment
                ON outfit_moment_tag(owner_person_id, moment_id);
                """
            )
            conn.commit()

    @staticmethod
    def _require_nonblank(value: str, field_name: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(f"{field_name} must not be blank")
        return value
