# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Quick vertical-slice smoke tests for both life-agent demo features."""

from __future__ import annotations

from pathlib import Path

from miloco.life.quick_e2e import build_quick_life_e2e, main

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "life_mimo_mock.json"


def test_build_quick_life_e2e_runs_outfit_cooking_notify_and_history(tmp_path):
    db_path = tmp_path / "quick-life.db"

    result = build_quick_life_e2e(FIXTURE_PATH, db_path)

    assert result.source_id == "demo_afternoon_interview_dinner"
    assert result.outfit_title == "深灰色西装外套、白色衬衫"
    assert result.cooking_title == "番茄鸡蛋配速冻饺子"
    assert result.notify_channel == "text"
    assert result.history_count == 2
    assert result.history_domains == ["cooking", "outfit"]
    assert "请先确认锅具状态和食材新鲜度" in result.cooking_broadcast_text
    assert "already cooked" not in result.report.lower()
    assert "must turn off" not in result.report.lower()


def test_quick_life_e2e_main_prints_reviewable_two_feature_report(tmp_path, capsys):
    db_path = tmp_path / "quick-life.db"

    exit_code = main([str(FIXTURE_PATH), "--db-path", str(db_path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Miloco Life Agent Quick E2E" in captured.out
    assert "Outfit flow: PASS" in captured.out
    assert "Cooking flow: PASS" in captured.out
    assert "Notify fallback: text" in captured.out
    assert "History count: 2" in captured.out
