# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""SQLite persistence seam for life-domain demo assets and recommendations."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from miloco.life.extractor import LifeExtractionResult
from miloco.life.schema import (
    LifeDomain,
    LifePreference,
    PantryItem,
    RecommendationResult,
    WardrobeItem,
)


class LifeRepo:
    """Small SQLite repo for reviewable life-agent demo state."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def save_extraction_result(self, assets: LifeExtractionResult) -> dict[str, Any]:
        now = _now_ms()
        with self._connect() as conn:
            for item in assets.wardrobe_items:
                conn.execute(
                    """
                    INSERT INTO life_wardrobe_item (
                        id, source_id, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_id=excluded.source_id,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item.id,
                        assets.source_id,
                        _model_json(item),
                        now,
                        now,
                    ),
                )
            for item in assets.pantry_items:
                conn.execute(
                    """
                    INSERT INTO life_pantry_item (
                        id, source_id, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_id=excluded.source_id,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        item.id,
                        assets.source_id,
                        _model_json(item),
                        now,
                        now,
                    ),
                )
            for index, preference in enumerate(assets.preferences):
                preference_id = _preference_id(assets.source_id, preference, index)
                conn.execute(
                    """
                    INSERT INTO life_preference (
                        id, source_id, payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        source_id=excluded.source_id,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at
                    """,
                    (
                        preference_id,
                        assets.source_id,
                        _model_json(preference),
                        now,
                        now,
                    ),
                )
            conn.commit()

        return {
            "source_id": assets.source_id,
            "wardrobe_count": len(assets.wardrobe_items),
            "pantry_count": len(assets.pantry_items),
            "preference_count": len(assets.preferences),
        }

    def list_wardrobe_items(self) -> list[WardrobeItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM life_wardrobe_item ORDER BY rowid"
            ).fetchall()
        return [WardrobeItem.model_validate_json(row["payload_json"]) for row in rows]

    def list_pantry_items(self) -> list[PantryItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM life_pantry_item ORDER BY rowid"
            ).fetchall()
        return [PantryItem.model_validate_json(row["payload_json"]) for row in rows]

    def list_preferences(self) -> list[LifePreference]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM life_preference ORDER BY rowid"
            ).fetchall()
        return [LifePreference.model_validate_json(row["payload_json"]) for row in rows]

    def record_recommendation(
        self,
        domain: LifeDomain,
        result: RecommendationResult,
        *,
        source_id: str | None = None,
    ) -> str:
        if domain != result.domain:
            raise ValueError("recommendation domain must match result.domain")
        recommendation_id = str(uuid.uuid4())
        now = _now_ms()
        option_titles = [option.title for option in result.options]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO life_recommendation_history (
                    id, domain, source_id, payload_json, option_titles_json,
                    broadcast_text, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation_id,
                    domain,
                    source_id,
                    _model_json(result),
                    json.dumps(option_titles, ensure_ascii=False),
                    result.broadcast_text,
                    now,
                ),
            )
            conn.commit()
        return recommendation_id

    def list_recommendation_history(
        self,
        *,
        domain: LifeDomain | None = None,
        source_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if limit is not None and limit < 1:
            raise ValueError("limit must be greater than 0")
        source_id = _normalize_optional_str(source_id)
        where_conditions: list[str] = []
        params: list[Any] = []
        if domain is not None:
            where_conditions.append("domain = ?")
            params.append(domain)
        if source_id is not None:
            where_conditions.append("source_id = ?")
            params.append(source_id)
        where_clause = ""
        if where_conditions:
            where_clause = f"WHERE {' AND '.join(where_conditions)}"
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT ?"
            params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT id, domain, source_id, option_titles_json, broadcast_text,
                       created_at
                FROM life_recommendation_history
                {where_clause}
                ORDER BY created_at DESC, id DESC
                {limit_clause}
                """.strip(),
                params,
            ).fetchall()
        return [
            {
                "id": row["id"],
                "domain": row["domain"],
                "source_id": row["source_id"],
                "option_titles": json.loads(row["option_titles_json"]),
                "broadcast_text": row["broadcast_text"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def summarize_recommendation_history(
        self,
        *,
        domain: LifeDomain | None = None,
        source_id: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        history = self.list_recommendation_history(
            domain=domain,
            source_id=source_id,
            limit=limit,
        )
        summary: dict[str, Any] = {
            "count": len(history),
            "history": history,
        }
        if not history:
            summary["history_hint"] = _empty_history_hint(domain, source_id)
        return summary

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS life_wardrobe_item (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS life_pantry_item (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS life_preference (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS life_recommendation_history (
                    id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    source_id TEXT,
                    payload_json TEXT NOT NULL,
                    option_titles_json TEXT NOT NULL,
                    broadcast_text TEXT,
                    created_at INTEGER NOT NULL
                );
                """
            )
            conn.commit()


def _model_json(model: Any) -> str:
    return model.model_dump_json()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _preference_id(source_id: str, preference: LifePreference, index: int) -> str:
    person = preference.person_id or "home"
    tags = "-".join(preference.tags) or str(index)
    return f"{source_id}:{preference.domain}:{person}:{tags}"


def _normalize_optional_str(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _empty_history_hint(domain: LifeDomain | None, source_id: str | None) -> str:
    label = f"{domain} recommendation history" if domain else "recommendation history"
    if source_id:
        label = f"{label} for source {source_id}"
    return (
        f"No {label} yet. Run the life demo with --persist before recording "
        "the history step."
    )
