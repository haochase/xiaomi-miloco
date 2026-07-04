"""life command tests for the hackathon demo CLI seam."""

from __future__ import annotations

import json

from click.testing import CliRunner

from miloco_cli.main import cli


def test_life_demo_posts_builtin_mock_payload(monkeypatch):
    calls = []

    def fake_post(path, body=None):
        calls.append((path, body))
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "source_id": "demo_afternoon_interview_dinner",
                "outfit": {"title": "Interview outfit"},
                "cooking": {"title": "30 minute dinner"},
                "cooking_broadcast_text": "The water may be boiling; please confirm before adding dumplings.",
            },
        }

    monkeypatch.setattr("miloco_cli.commands.life.api_post", fake_post)

    result = CliRunner().invoke(cli, ["life", "demo"])

    assert result.exit_code == 0
    assert calls[0][0] == "/api/life/demo"
    payload = calls[0][1]
    assert payload["mimo_payload"]["source_id"] == "demo_afternoon_interview_dinner"
    assert payload["occasion"] == "tomorrow morning interview"
    assert payload["people_count"] == 3
    assert payload["time_budget_minutes"] == 30
    data = json.loads(result.output)
    assert data["data"]["outfit"]["title"] == "Interview outfit"


def test_life_demo_posts_fixture_payload(tmp_path, monkeypatch):
    fixture = tmp_path / "mimo.json"
    fixture.write_text(
        json.dumps(
            {
                "source_id": "fixture_case",
                "caption": "mock MiMo fixture",
                "wardrobe": [],
                "pantry": [],
                "preferences": [],
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_post(path, body=None):
        calls.append((path, body))
        return {"code": 0, "message": "ok", "data": {"source_id": "fixture_case"}}

    monkeypatch.setattr("miloco_cli.commands.life.api_post", fake_post)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "demo",
            "--fixture",
            str(fixture),
            "--occasion",
            "rainy commute",
            "--people-count",
            "2",
            "--time-budget-minutes",
            "20",
            "--pretty",
        ],
    )

    assert result.exit_code == 0
    assert calls[0][1]["mimo_payload"]["source_id"] == "fixture_case"
    assert calls[0][1]["occasion"] == "rainy commute"
    assert calls[0][1]["people_count"] == 2
    assert calls[0][1]["time_budget_minutes"] == 20
    assert "\n  " in result.output


def test_life_demo_can_request_persistence(tmp_path, monkeypatch):
    db_path = tmp_path / "life-demo.db"
    calls = []

    def fake_post(path, body=None):
        calls.append((path, body))
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "source_id": "demo_afternoon_interview_dinner",
                "persistence": {
                    "wardrobe_count": 3,
                    "pantry_count": 4,
                    "recommendation_history_count": 2,
                },
            },
        }

    monkeypatch.setattr("miloco_cli.commands.life.api_post", fake_post)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "demo",
            "--persist",
            "--db-path",
            str(db_path),
        ],
    )

    assert result.exit_code == 0
    assert calls[0][0] == "/api/life/demo"
    assert calls[0][1]["persist"] is True
    assert calls[0][1]["db_path"] == str(db_path)
    data = json.loads(result.output)
    assert data["data"]["persistence"]["recommendation_history_count"] == 2


def test_life_history_gets_persisted_recommendations(tmp_path, monkeypatch):
    db_path = tmp_path / "life-demo.db"
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "db_path": str(db_path),
                "count": 1,
                "history": [
                    {
                        "domain": "cooking",
                        "source_id": "demo_afternoon_interview_dinner",
                        "option_titles": ["tomato eggs, greens, and frozen dumplings"],
                        "broadcast_text": "The water may be boiling; Please confirm before adding dumplings.",
                    }
                ],
            },
        }

    monkeypatch.setattr("miloco_cli.commands.life.api_get", fake_get)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "history",
            "--db-path",
            str(db_path),
            "--domain",
            "cooking",
            "--limit",
            "1",
            "--pretty",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "/api/life/history",
            {
                "db_path": str(db_path),
                "domain": "cooking",
                "limit": 1,
            },
        )
    ]
    data = json.loads(result.output)
    assert data["data"]["history"][0]["domain"] == "cooking"
    assert "Please confirm" in result.output


def test_life_history_can_filter_by_source_id(tmp_path, monkeypatch):
    db_path = tmp_path / "life-demo.db"
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "db_path": str(db_path),
                "source_id": "demo_afternoon_interview_dinner",
                "count": 1,
                "history": [
                    {
                        "domain": "outfit",
                        "source_id": "demo_afternoon_interview_dinner",
                        "option_titles": ["dark gray blazer, white shirt"],
                    }
                ],
            },
        }

    monkeypatch.setattr("miloco_cli.commands.life.api_get", fake_get)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "history",
            "--db-path",
            str(db_path),
            "--source-id",
            "demo_afternoon_interview_dinner",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "/api/life/history",
            {
                "db_path": str(db_path),
                "limit": 10,
                "source_id": "demo_afternoon_interview_dinner",
            },
        )
    ]
    data = json.loads(result.output)
    assert data["data"]["history"][0]["source_id"] == "demo_afternoon_interview_dinner"


def test_life_history_prints_empty_history_hint(tmp_path, monkeypatch):
    db_path = tmp_path / "life-demo.db"

    def fake_get(path, params=None):
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "db_path": str(db_path),
                "domain": "cooking",
                "count": 0,
                "history": [],
                "history_hint": (
                    "No cooking recommendation history yet. Run the life demo with "
                    "--persist before recording the history step."
                ),
            },
        }

    monkeypatch.setattr("miloco_cli.commands.life.api_get", fake_get)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "history",
            "--db-path",
            str(db_path),
            "--domain",
            "cooking",
            "--pretty",
        ],
    )

    assert result.exit_code == 0
    assert "No cooking recommendation history yet" in result.output
    assert "--persist" in result.output


def test_life_notify_posts_conservative_message(monkeypatch):
    calls = []

    def fake_post(path, body=None):
        calls.append((path, body))
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "channel": "text",
                "delivered": False,
                "fallback_text": body["message"],
                "requires_ack": True,
                "reason": "pc_speaker_url not configured",
            },
        }

    monkeypatch.setattr("miloco_cli.commands.life.api_post", fake_post)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "notify",
            "--message",
            "The water may be boiling; please confirm before adding dumplings.",
            "--domain",
            "cooking",
            "--urgency",
            "medium",
            "--requires-ack",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "/api/life/notify",
            {
                "message": "The water may be boiling; please confirm before adding dumplings.",
                "domain": "cooking",
                "urgency": "medium",
                "requires_ack": True,
                "fallback_to_text": True,
            },
        )
    ]
    data = json.loads(result.output)
    assert data["data"]["fallback_text"].startswith("The water may be")


def test_life_trigger_posts_schedule_outfit_without_visual_input(monkeypatch):
    calls = []

    def fake_post(path, body=None):
        calls.append((path, body))
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "trigger_source": "schedule",
                "domain": "outfit",
                "used_visual_input": False,
                "camera_required": False,
                "outfit": {"title": "dark gray blazer, white shirt"},
            },
        }

    monkeypatch.setattr("miloco_cli.commands.life.api_post", fake_post)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "trigger",
            "--trigger-source",
            "schedule",
            "--domain",
            "outfit",
            "--occasion",
            "08:30 outfit reminder",
            "--weather",
            "cool rainy morning",
            "--db-path",
            "data/life-demo.db",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "/api/life/trigger",
            {
                "trigger_source": "schedule",
                "domain": "outfit",
                "occasion": "08:30 outfit reminder",
                "weather": "cool rainy morning",
                "people_count": 1,
                "time_budget_minutes": 30,
                "persist": True,
                "db_path": "data/life-demo.db",
            },
        )
    ]
    data = json.loads(result.output)
    assert data["data"]["used_visual_input"] is False


def test_life_text_trigger_posts_voice_command_without_visual_input(monkeypatch):
    calls = []

    def fake_post(path, body=None):
        calls.append((path, body))
        return {
            "code": 0,
            "message": "ok",
            "data": {
                "matched": True,
                "action": "needs_visual_capture",
                "domain": "outfit",
                "camera_required": True,
                "needs_visual_capture": True,
            },
        }

    monkeypatch.setattr("miloco_cli.commands.life.api_post", fake_post)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "text-trigger",
            "--text",
            "帮我看看这件衣服怎么搭",
            "--occasion",
            "video meeting",
            "--weather",
            "indoor",
            "--db-path",
            "data/life-demo.db",
            "--pretty",
        ],
    )

    assert result.exit_code == 0
    assert calls == [
        (
            "/api/life/trigger",
            {
                "text": "帮我看看这件衣服怎么搭",
                "trigger_source": "voice_intent",
                "occasion": "video meeting",
                "weather": "indoor",
                "people_count": 1,
                "time_budget_minutes": 30,
                "persist": True,
                "db_path": "data/life-demo.db",
            },
        )
    ]
    data = json.loads(result.output)
    assert data["data"]["needs_visual_capture"] is True


def test_life_notify_can_target_pc_speaker_url(monkeypatch):
    calls = []

    def fake_post(path, body=None):
        calls.append((path, body))
        return {"code": 0, "message": "ok", "data": {"channel": "pc_speaker"}}

    monkeypatch.setattr("miloco_cli.commands.life.api_post", fake_post)

    result = CliRunner().invoke(
        cli,
        [
            "life",
            "notify",
            "--message",
            "The timer is at 6 minutes; please check the dumplings.",
            "--domain",
            "cooking",
            "--pc-speaker-url",
            "http://127.0.0.1:18888/say",
            "--no-fallback-to-text",
        ],
    )

    assert result.exit_code == 0
    assert calls[0][1]["pc_speaker_url"] == "http://127.0.0.1:18888/say"
    assert calls[0][1]["fallback_to_text"] is False
