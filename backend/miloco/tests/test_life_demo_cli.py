# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""CLI smoke tests for the life-domain hackathon demo."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from miloco.life.demo import build_life_demo_report, main

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "life_mimo_mock.json"


def test_build_life_demo_report_chains_fixture_to_recommendations():
    report = build_life_demo_report(FIXTURE_PATH)

    assert "Miloco Life Agent Demo" in report
    assert "Mock MiMo source: demo_afternoon_interview_dinner" in report
    assert "Outfit: 深灰色西装外套、白色衬衫" in report
    assert "Cooking: 番茄鸡蛋配速冻饺子" in report
    assert "请先确认锅具状态和食材新鲜度" in report
    assert "Low confidence notes:" in report


def test_main_prints_report_for_fixture(capsys):
    exit_code = main([str(FIXTURE_PATH)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Miloco Life Agent Demo" in captured.out
    assert "深灰色西装外套" in captured.out
    assert "速冻饺子" in captured.out


def test_python_module_entrypoint_runs_demo_fixture():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "miloco.life.demo",
            str(FIXTURE_PATH),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Mock MiMo source: demo_afternoon_interview_dinner" in result.stdout
    assert "请先确认锅具状态和食材新鲜度" in result.stdout
