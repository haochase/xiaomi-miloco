# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Owner-scoped SQLite persistence for confirmed Outfit wardrobe items."""

from __future__ import annotations

import json
import sqlite3

from miloco.outfit.storage import OutfitStorage
from miloco.outfit.wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeItemDraft,
    WardrobeSourceEvidence,
    requires_exact_source_deduplication,
)


class DuplicateWardrobeSourceError(ValueError):
    """Raised when an owner confirms an existing stable external source again."""


class WardrobeRepository:
    """Persist confirmed items and expose only owner-scoped available inventory."""

    def __init__(self, storage: OutfitStorage) -> None:
        self._storage = storage
        self._ensure_schema()

    def add_confirmed_item(self, item: ConfirmedWardrobeItem) -> None:
        """Persist one explicitly confirmed item with conservative source deduplication."""

        source_evidence_json = json.dumps(
            [evidence.model_dump(mode="json") for evidence in item.source_evidence],
            separators=(",", ":"),
            sort_keys=True,
        )

        try:
            with self._storage.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO outfit_confirmed_wardrobe_items (
                        item_id,
                        owner_person_id,
                        name,
                        category,
                        source_evidence_json,
                        confirmed_at_ms,
                        availability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.item_id,
                        item.owner_person_id,
                        item.name,
                        item.category,
                        source_evidence_json,
                        item.confirmed_at_ms,
                        item.availability,
                    ),
                )
                self._insert_external_source_keys(connection, item)
        except sqlite3.IntegrityError as exc:
            if self._has_conflicting_external_source(item):
                raise DuplicateWardrobeSourceError(
                    "external wardrobe source is already confirmed for this owner"
                ) from exc
            raise

    def confirm_pending_draft(
        self,
        *,
        draft_id: str,
        item: ConfirmedWardrobeItem,
    ) -> ConfirmedWardrobeItem:
        """Insert an item and close its owner-scoped draft in one transaction."""

        owner_person_id = _require_owner_person_id(item.owner_person_id)
        source_evidence_json = json.dumps(
            [evidence.model_dump(mode="json") for evidence in item.source_evidence],
            separators=(",", ":"),
            sort_keys=True,
        )
        try:
            with self._storage.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                draft_row = connection.execute(
                    """
                    SELECT status
                    FROM outfit_wardrobe_drafts
                    WHERE owner_person_id = ? AND draft_id = ?
                    """,
                    (owner_person_id, draft_id),
                ).fetchone()
                existing_row = connection.execute(
                    """
                    SELECT
                        item_id,
                        owner_person_id,
                        name,
                        category,
                        source_evidence_json,
                        confirmed_at_ms,
                        availability
                    FROM outfit_confirmed_wardrobe_items
                    WHERE owner_person_id = ? AND item_id = ?
                    """,
                    (owner_person_id, item.item_id),
                ).fetchone()
                if existing_row is not None:
                    existing_item = _confirmed_item_from_row(existing_row)
                    if not _same_confirmation_identity(existing_item, item):
                        raise ValueError(
                            "confirmed wardrobe item does not match pending draft"
                        )
                    if draft_row is not None and draft_row["status"] == "pending":
                        connection.execute(
                            """
                            UPDATE outfit_wardrobe_drafts
                            SET status = 'confirmed'
                            WHERE owner_person_id = ?
                                AND draft_id = ?
                                AND status = 'pending'
                            """,
                            (owner_person_id, draft_id),
                        )
                    return existing_item

                if draft_row is None:
                    raise ValueError("wardrobe draft not found")
                if draft_row["status"] != "pending":
                    raise ValueError("wardrobe draft is no longer pending")

                connection.execute(
                    """
                    INSERT INTO outfit_confirmed_wardrobe_items (
                        item_id,
                        owner_person_id,
                        name,
                        category,
                        source_evidence_json,
                        confirmed_at_ms,
                        availability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.item_id,
                        owner_person_id,
                        item.name,
                        item.category,
                        source_evidence_json,
                        item.confirmed_at_ms,
                        item.availability,
                    ),
                )
                self._insert_external_source_keys(connection, item)
                transition = connection.execute(
                    """
                    UPDATE outfit_wardrobe_drafts
                    SET status = 'confirmed'
                    WHERE owner_person_id = ? AND draft_id = ? AND status = 'pending'
                    """,
                    (owner_person_id, draft_id),
                )
                if transition.rowcount != 1:
                    raise ValueError("wardrobe draft is no longer pending")
        except sqlite3.IntegrityError as exc:
            if self._has_conflicting_external_source(item):
                raise DuplicateWardrobeSourceError(
                    "external wardrobe source is already confirmed for this owner"
                ) from exc
            raise
        return item

    def add_pending_draft(self, draft: WardrobeItemDraft) -> None:
        """Persist one pending draft without making it recommendation-eligible."""

        source_evidence_json = json.dumps(
            [evidence.model_dump(mode="json") for evidence in draft.source_evidence],
            separators=(",", ":"),
            sort_keys=True,
        )
        with self._storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO outfit_wardrobe_drafts (
                    draft_id,
                    owner_person_id,
                    name,
                    category,
                    source_evidence_json,
                    created_at_ms,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.draft_id,
                    draft.owner_person_id,
                    draft.name,
                    draft.category,
                    source_evidence_json,
                    draft.created_at_ms,
                    draft.status,
                ),
            )

    def get_draft_for_owner(
        self,
        owner_person_id: str,
        draft_id: str,
    ) -> WardrobeItemDraft | None:
        """Return one owner-scoped pending draft."""

        normalized_owner_person_id = _require_owner_person_id(owner_person_id)
        with self._storage.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    draft_id,
                    owner_person_id,
                    name,
                    category,
                    source_evidence_json,
                    created_at_ms,
                    status
                FROM outfit_wardrobe_drafts
                WHERE owner_person_id = ? AND draft_id = ? AND status = 'pending'
                """,
                (normalized_owner_person_id, draft_id),
            ).fetchone()
        return _draft_from_row(row) if row is not None else None

    def list_pending_drafts(
        self,
        owner_person_id: str,
    ) -> tuple[WardrobeItemDraft, ...]:
        """Return pending drafts for one owner without exposing another owner's data."""

        normalized_owner_person_id = _require_owner_person_id(owner_person_id)
        with self._storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    draft_id,
                    owner_person_id,
                    name,
                    category,
                    source_evidence_json,
                    created_at_ms,
                    status
                FROM outfit_wardrobe_drafts
                WHERE owner_person_id = ? AND status = 'pending'
                ORDER BY created_at_ms ASC, draft_id ASC
                """,
                (normalized_owner_person_id,),
            ).fetchall()
        return tuple(_draft_from_row(row) for row in rows)

    def get_confirmed_item_for_owner(
        self,
        owner_person_id: str,
        item_id: str,
    ) -> ConfirmedWardrobeItem | None:
        """Return one confirmed item for idempotent owner-scoped confirmation."""

        normalized_owner_person_id = _require_owner_person_id(owner_person_id)
        with self._storage.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    item_id,
                    owner_person_id,
                    name,
                    category,
                    source_evidence_json,
                    confirmed_at_ms,
                    availability
                FROM outfit_confirmed_wardrobe_items
                WHERE owner_person_id = ? AND item_id = ?
                """,
                (normalized_owner_person_id, item_id),
            ).fetchone()
        return _confirmed_item_from_row(row) if row is not None else None

    def list_confirmed_available_items(
        self,
        owner_person_id: str,
    ) -> tuple[ConfirmedWardrobeItem, ...]:
        """Return the stable, recommendation-eligible inventory for one owner."""

        normalized_owner_person_id = _require_owner_person_id(owner_person_id)
        with self._storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    item_id,
                    owner_person_id,
                    name,
                    category,
                    source_evidence_json,
                    confirmed_at_ms,
                    availability
                FROM outfit_confirmed_wardrobe_items
                WHERE owner_person_id = ? AND availability = 'available'
                ORDER BY confirmed_at_ms ASC, item_id ASC
                """,
                (normalized_owner_person_id,),
            ).fetchall()

        return tuple(_confirmed_item_from_row(row) for row in rows)

    def _ensure_schema(self) -> None:
        with self._storage.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_confirmed_wardrobe_items (
                    owner_person_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source_evidence_json TEXT NOT NULL,
                    confirmed_at_ms INTEGER NOT NULL,
                    availability TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, item_id)
                );

                CREATE INDEX IF NOT EXISTS outfit_confirmed_wardrobe_owner_available_idx
                ON outfit_confirmed_wardrobe_items (owner_person_id, availability);

                CREATE TABLE IF NOT EXISTS outfit_wardrobe_drafts (
                    owner_person_id TEXT NOT NULL,
                    draft_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source_evidence_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, draft_id)
                );

                CREATE INDEX IF NOT EXISTS outfit_wardrobe_drafts_owner_status_idx
                ON outfit_wardrobe_drafts (owner_person_id, status);

                CREATE TABLE IF NOT EXISTS outfit_confirmed_wardrobe_external_sources (
                    owner_person_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, source_type, source_reference),
                    FOREIGN KEY (owner_person_id, item_id)
                        REFERENCES outfit_confirmed_wardrobe_items (
                            owner_person_id,
                            item_id
                        )
                        ON DELETE CASCADE
                );
                """
            )

    def _insert_external_source_keys(
        self,
        connection: sqlite3.Connection,
        item: ConfirmedWardrobeItem,
    ) -> None:
        for evidence in item.source_evidence:
            if requires_exact_source_deduplication(evidence.source_type):
                connection.execute(
                    """
                    INSERT INTO outfit_confirmed_wardrobe_external_sources (
                        owner_person_id,
                        source_type,
                        source_reference,
                        item_id
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        item.owner_person_id,
                        evidence.source_type,
                        evidence.reference,
                        item.item_id,
                    ),
                )

    def _has_conflicting_external_source(self, item: ConfirmedWardrobeItem) -> bool:
        with self._storage.connect() as connection:
            for evidence in item.source_evidence:
                if not requires_exact_source_deduplication(evidence.source_type):
                    continue
                row = connection.execute(
                    """
                    SELECT 1
                    FROM outfit_confirmed_wardrobe_external_sources
                    WHERE owner_person_id = ?
                        AND source_type = ?
                        AND source_reference = ?
                    """,
                    (
                        item.owner_person_id,
                        evidence.source_type,
                        evidence.reference,
                    ),
                ).fetchone()
                if row is not None:
                    return True
        return False


def _confirmed_item_from_row(row: sqlite3.Row) -> ConfirmedWardrobeItem:
    source_evidence = tuple(
        WardrobeSourceEvidence.model_validate(evidence)
        for evidence in json.loads(row["source_evidence_json"])
    )
    return ConfirmedWardrobeItem(
        item_id=row["item_id"],
        owner_person_id=row["owner_person_id"],
        name=row["name"],
        category=row["category"],
        source_evidence=source_evidence,
        confirmed_at_ms=row["confirmed_at_ms"],
        confirmed_by_user=True,
        availability=row["availability"],
    )


def _draft_from_row(row: sqlite3.Row) -> WardrobeItemDraft:
    source_evidence = tuple(
        WardrobeSourceEvidence.model_validate(evidence)
        for evidence in json.loads(row["source_evidence_json"])
    )
    return WardrobeItemDraft(
        draft_id=row["draft_id"],
        owner_person_id=row["owner_person_id"],
        name=row["name"],
        category=row["category"],
        source_evidence=source_evidence,
        created_at_ms=row["created_at_ms"],
        status=row["status"],
    )


def _same_confirmation_identity(
    existing_item: ConfirmedWardrobeItem,
    pending_item: ConfirmedWardrobeItem,
) -> bool:
    return (
        existing_item.owner_person_id == pending_item.owner_person_id
        and existing_item.item_id == pending_item.item_id
        and existing_item.name == pending_item.name
        and existing_item.category == pending_item.category
        and existing_item.source_evidence == pending_item.source_evidence
    )


def _require_owner_person_id(owner_person_id: str) -> str:
    normalized_owner_person_id = owner_person_id.strip()
    if not normalized_owner_person_id:
        raise ValueError("owner_person_id must not be blank")
    return normalized_owner_person_id
