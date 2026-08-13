# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Owner-bound persistence for private Outfit wardrobe drafts and items."""

from __future__ import annotations

from pathlib import Path

from miloco.life.outfit_storage import OutfitStorage
from miloco.life.outfit_wardrobe import (
    ConfirmedWardrobeItem,
    WardrobeDraftStatus,
    WardrobeItemDraft,
)


class OutfitWardrobeRepo:
    """Persist drafts separately from confirmed inventory in the plugin database."""

    def __init__(self, storage: OutfitStorage | str | Path):
        self._storage = (
            storage if isinstance(storage, OutfitStorage) else OutfitStorage(storage)
        )
        self._init_schema()

    def save_draft_or_get(self, draft: WardrobeItemDraft) -> WardrobeItemDraft:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO outfit_wardrobe_draft (
                    owner_person_id, draft_id, status, created_at_ms, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    draft.owner_person_id,
                    draft.draft_id,
                    draft.status,
                    draft.created_at_ms,
                    draft.model_dump_json(),
                ),
            )
            row = conn.execute(
                """
                SELECT payload_json FROM outfit_wardrobe_draft
                WHERE owner_person_id = ? AND draft_id = ?
                """,
                (draft.owner_person_id, draft.draft_id),
            ).fetchone()
        return WardrobeItemDraft.model_validate_json(row["payload_json"])

    def update_draft(self, draft: WardrobeItemDraft) -> WardrobeItemDraft:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE outfit_wardrobe_draft
                SET status = ?, payload_json = ?
                WHERE owner_person_id = ? AND draft_id = ?
                """,
                (
                    draft.status,
                    draft.model_dump_json(),
                    draft.owner_person_id,
                    draft.draft_id,
                ),
            )
        if cursor.rowcount != 1:
            raise ValueError("wardrobe draft not found")
        return draft

    def get_draft_for_owner(
        self, owner_person_id: str, draft_id: str
    ) -> WardrobeItemDraft | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM outfit_wardrobe_draft
                WHERE owner_person_id = ? AND draft_id = ?
                """,
                (owner_person_id, draft_id),
            ).fetchone()
        return (
            WardrobeItemDraft.model_validate_json(row["payload_json"])
            if row is not None
            else None
        )

    def list_drafts_for_owner(
        self, owner_person_id: str, *, status: WardrobeDraftStatus
    ) -> list[WardrobeItemDraft]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM outfit_wardrobe_draft
                WHERE owner_person_id = ? AND status = ?
                ORDER BY created_at_ms, draft_id
                """,
                (owner_person_id, status),
            ).fetchall()
        return [
            WardrobeItemDraft.model_validate_json(row["payload_json"]) for row in rows
        ]

    def save_item_or_get(self, item: ConfirmedWardrobeItem) -> ConfirmedWardrobeItem:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO outfit_wardrobe_item (
                    owner_person_id,
                    item_id,
                    source_type,
                    source_reference,
                    confirmed_at_ms,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.owner_person_id,
                    item.item_id,
                    item.source_type,
                    item.source_reference,
                    item.confirmed_at_ms,
                    item.model_dump_json(),
                ),
            )
            row = conn.execute(
                """
                SELECT payload_json FROM outfit_wardrobe_item
                WHERE owner_person_id = ? AND item_id = ?
                """,
                (item.owner_person_id, item.item_id),
            ).fetchone()
        return ConfirmedWardrobeItem.model_validate_json(row["payload_json"])

    def get_item_for_owner(
        self, owner_person_id: str, item_id: str
    ) -> ConfirmedWardrobeItem | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json FROM outfit_wardrobe_item
                WHERE owner_person_id = ? AND item_id = ?
                """,
                (owner_person_id, item_id),
            ).fetchone()
        return (
            ConfirmedWardrobeItem.model_validate_json(row["payload_json"])
            if row is not None
            else None
        )

    def update_item(self, item: ConfirmedWardrobeItem) -> ConfirmedWardrobeItem:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE outfit_wardrobe_item
                SET payload_json = ?
                WHERE owner_person_id = ? AND item_id = ?
                """,
                (item.model_dump_json(), item.owner_person_id, item.item_id),
            )
        if cursor.rowcount != 1:
            raise ValueError("wardrobe item not found")
        return item

    def delete_item_for_owner(self, owner_person_id: str, item_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                DELETE FROM outfit_wardrobe_item
                WHERE owner_person_id = ? AND item_id = ?
                """,
                (owner_person_id, item_id),
            )
        return cursor.rowcount == 1

    def has_exact_source(
        self, owner_person_id: str, *, source_type: str, source_reference: str
    ) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM outfit_wardrobe_item
                WHERE owner_person_id = ?
                  AND source_type = ?
                  AND source_reference = ?
                """,
                (owner_person_id, source_type, source_reference),
            ).fetchone()
        return row is not None

    def list_items_for_owner(self, owner_person_id: str) -> list[ConfirmedWardrobeItem]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload_json FROM outfit_wardrobe_item
                WHERE owner_person_id = ?
                ORDER BY confirmed_at_ms, item_id
                """,
                (owner_person_id,),
            ).fetchall()
        return [
            ConfirmedWardrobeItem.model_validate_json(row["payload_json"])
            for row in rows
        ]

    def _connect(self):
        return self._storage.connect()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            if self._has_legacy_item_source_constraint(conn):
                self._migrate_legacy_item_source_constraint(conn)
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS outfit_wardrobe_draft (
                    owner_person_id TEXT NOT NULL,
                    draft_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, draft_id)
                );

                CREATE TABLE IF NOT EXISTS outfit_wardrobe_item (
                    owner_person_id TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    source_reference TEXT NOT NULL,
                    confirmed_at_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (owner_person_id, item_id)
                );

                CREATE INDEX IF NOT EXISTS idx_outfit_wardrobe_item_owner
                ON outfit_wardrobe_item(owner_person_id);

                CREATE UNIQUE INDEX IF NOT EXISTS
                idx_outfit_wardrobe_item_external_source
                ON outfit_wardrobe_item(owner_person_id, source_type, source_reference)
                WHERE source_type IN ('photo', 'product_link');
                """
            )

    def _has_legacy_item_source_constraint(self, conn) -> bool:
        row = conn.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'outfit_wardrobe_item'
            """
        ).fetchone()
        if row is None:
            return False
        schema_sql = "".join(str(row["sql"] or "").lower().split())
        return "unique(owner_person_id,source_type,source_reference)" in schema_sql

    def _migrate_legacy_item_source_constraint(self, conn) -> None:
        conn.executescript(
            """
            ALTER TABLE outfit_wardrobe_item
            RENAME TO outfit_wardrobe_item_legacy;

            CREATE TABLE outfit_wardrobe_item (
                owner_person_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                confirmed_at_ms INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (owner_person_id, item_id)
            );

            INSERT INTO outfit_wardrobe_item (
                owner_person_id,
                item_id,
                source_type,
                source_reference,
                confirmed_at_ms,
                payload_json
            )
            SELECT
                owner_person_id,
                item_id,
                source_type,
                source_reference,
                confirmed_at_ms,
                payload_json
            FROM outfit_wardrobe_item_legacy;

            DROP TABLE outfit_wardrobe_item_legacy;
            """
        )
