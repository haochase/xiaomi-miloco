# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Configured-runtime contracts for Outfit moment persistence."""

import sqlite3
from pathlib import Path

import pytest
from miloco.life.outfit_feedback_events import OutfitFeedbackEvent
from miloco.life.outfit_installation import OutfitRuntimeContext
from miloco.life.outfit_moment_runtime import build_outfit_moment_runtime


def test_runtime_uses_configured_paths_and_bound_primary_owner(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_dir = tmp_path / "miloco-home"
    unrelated_cwd = tmp_path / "unrelated-cwd"
    workspace_dir.mkdir()
    unrelated_cwd.mkdir()
    context = OutfitRuntimeContext(
        primary_person_id="primary-person",
        workspace_dir=workspace_dir,
        storage_dir=workspace_dir / "outfit",
    )
    monkeypatch.chdir(unrelated_cwd)

    runtime = build_outfit_moment_runtime(context, clock_ms=lambda: 2_000)
    event = OutfitFeedbackEvent(
        event_id="wear-1",
        owner_person_id="primary-person",
        event_type="wear_confirmed",
        recommendation_id="recommendation-1",
        item_ids=("top-1", "bottom-1", "shoes-1"),
        occurred_at_ms=1_000,
        confirmed_by_user=True,
    )
    runtime.feedback_event_repo.append(event)

    moment = runtime.project_confirmed_wear(event_id="wear-1", timezone="Asia/Shanghai")

    assert runtime.primary_person_id == "primary-person"
    assert runtime.database_path == workspace_dir / "outfit" / "outfit.db"
    assert runtime.feedback_event_db_path == runtime.database_path
    assert runtime.moment_db_path == runtime.database_path
    assert runtime.media_db_path == runtime.database_path
    assert runtime.media_root == workspace_dir / "outfit" / "media"
    assert moment.owner_person_id == "primary-person"
    assert (
        runtime.moment_repo.get_for_owner("primary-person", moment.moment_id) == moment
    )
    assert not (unrelated_cwd / "data").exists()


def test_runtime_rejects_storage_outside_configured_workspace(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "miloco-home"
    context = OutfitRuntimeContext(
        primary_person_id="primary-person",
        workspace_dir=workspace_dir,
        storage_dir=tmp_path / "outside-workspace",
    )

    with pytest.raises(ValueError, match="inside the configured workspace"):
        build_outfit_moment_runtime(context, clock_ms=lambda: 2_000)


def test_runtime_initializes_all_outfit_metadata_in_one_private_database(
    tmp_path: Path,
) -> None:
    workspace_dir = tmp_path / "miloco-home"
    workspace_dir.mkdir()
    runtime = build_outfit_moment_runtime(
        OutfitRuntimeContext(
            primary_person_id="primary-person",
            workspace_dir=workspace_dir,
            storage_dir=workspace_dir / "outfit",
        ),
        clock_ms=lambda: 2_000,
    )

    with sqlite3.connect(runtime.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {
        "outfit_feedback_event",
        "outfit_moment",
        "outfit_moment_tag",
        "outfit_media_asset",
    } <= tables


def test_runtime_rejects_blank_primary_person(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "miloco-home"
    context = OutfitRuntimeContext(
        primary_person_id=" ",
        workspace_dir=workspace_dir,
        storage_dir=workspace_dir / "outfit",
    )

    with pytest.raises(ValueError, match="primary person id must not be blank"):
        build_outfit_moment_runtime(context, clock_ms=lambda: 2_000)
