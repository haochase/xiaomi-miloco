# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Mock MiMo extraction tests for life domain demo fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from miloco.life.extractor import extract_life_assets_from_mimo_mock
from miloco.life.mimo_live import (
    _extract_live_mimo_response_text,
    normalize_live_mimo_life_payload,
)
from miloco.perception.engine.omni.omni_client import OmniError

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_extracts_life_assets_from_mimo_mock_fixture():
    payload = json.loads((FIXTURE_DIR / "life_mimo_mock.json").read_text())

    result = extract_life_assets_from_mimo_mock(payload)

    assert [item.id for item in result.wardrobe_items] == [
        "blazer_gray",
        "shirt_white",
    ]
    assert [item.source_type for item in result.wardrobe_items] == [
        "mimo_mock",
        "mimo_mock",
    ]
    assert [item.id for item in result.pantry_items] == [
        "egg_1",
        "tomato_1",
        "dumpling_1",
    ]
    assert result.preferences[0].tags == ["not flashy", "formal enough"]
    assert result.source_id == "demo_afternoon_interview_dinner"
    assert result.low_confidence_notes == [
        "dumpling package brand is not recognized; please confirm before recording exact brand"
    ]


def test_extracts_basic_life_assets_from_demo_text():
    result = extract_life_assets_from_mimo_mock(
        "For tomorrow's interview: dark gray blazer and white shirt. "
        "For dinner: eggs, tomatoes, greens, and frozen dumplings for three people."
    )

    assert [item.name for item in result.wardrobe_items] == [
        "dark gray blazer",
        "white shirt",
    ]
    assert [item.name for item in result.pantry_items] == [
        "eggs",
        "tomatoes",
        "greens",
        "frozen dumplings",
    ]
    assert result.preferences[0].domain == "outfit"
    assert "mock text heuristic" in result.low_confidence_notes[0]


def test_normalizes_live_mimo_payload_into_life_schema():
    result = normalize_live_mimo_life_payload(
        {
            "source_id": "live_camera_probe_1182348802",
            "wardrobe": [
                {
                    "id": "w_001",
                    "name": "白色短袖Polo衫",
                    "category": "top",
                    "colors": ["white", "red", "blue"],
                    "material_tags": ["cotton"],
                    "season_tags": ["summer", "all"],
                    "formality": "casual",
                    "warmth_level": 0,
                    "style_tags": ["sporty", "casual"],
                    "source_type": "camera",
                    "source_ref": "00:00",
                    "confidence": 0.9,
                    "notes": "带有红蓝条纹装饰的白色Polo衫",
                }
            ],
            "pantry": [],
            "preferences": {"style": "casual", "diet": "unknown"},
            "low_confidence_notes": [
                "由于画面模糊，无法确认裤子和鞋子的具体款式和颜色"
            ],
        }
    )

    assert result.source_id == "live_camera_probe_1182348802"
    assert result.wardrobe_items[0].formality == 2
    assert result.wardrobe_items[0].warmth_level == 1
    assert result.wardrobe_items[0].season_tags == ["summer"]
    assert result.preferences[0].domain == "outfit"
    assert result.preferences[0].tags == ["casual"]
    assert "画面模糊" in result.low_confidence_notes[0]


def test_live_mimo_payload_rejects_non_json_text_with_omni_error():
    with pytest.raises(OmniError, match="not valid JSON"):
        normalize_live_mimo_life_payload("这件衣服看起来适合日常穿搭。")


def test_live_mimo_empty_content_reports_response_shape():
    raw = {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "model thought placeholder",
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 0},
    }

    with pytest.raises(OmniError) as exc_info:
        _extract_live_mimo_response_text(raw)

    message = str(exc_info.value)
    assert "empty content" in message
    assert "finish_reason=stop" in message
    assert "message_keys=[content, reasoning_content, role]" in message
    assert "usage_keys=[completion_tokens, prompt_tokens]" in message


def test_live_mimo_payload_accepts_markdown_wrapped_json():
    result = normalize_live_mimo_life_payload(
        """
        下面是结构化结果：

        ```json
        {
          "source_id": "camera_clip",
          "caption": "衣柜区域有几件衣服。",
          "wardrobe": [
            {
              "id": "w_001",
              "name": "橙色长袖上衣",
              "category": "top",
              "colors": ["橙色"],
              "formality": 2,
              "warmth_level": 2,
              "source_type": "camera",
              "confidence": 0.78
            }
          ],
          "pantry": [],
          "preferences": [],
          "low_confidence_notes": []
        }
        ```
        """,
    )

    assert result.source_id == "camera_clip"
    assert result.wardrobe_items[0].name == "橙色长袖上衣"


def test_live_mimo_truncated_json_reports_parse_context():
    payload = '{"source_id":"camera_clip","wardrobe":[{"id":"w_001"'

    with pytest.raises(OmniError) as exc_info:
        normalize_live_mimo_life_payload(payload)

    message = str(exc_info.value)
    assert "not valid JSON" in message
    assert "content_chars=52" in message
