# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Notify adapter tests for the life-domain demo."""

from __future__ import annotations

import httpx
from miloco.life.notify import LifeNotifyRequest, deliver_life_notification


def test_deliver_life_notification_falls_back_to_text_without_url():
    result = deliver_life_notification(
        LifeNotifyRequest(
            message="Water may be boiling; please confirm before adding dumplings.",
            domain="cooking",
            urgency="medium",
            requires_ack=True,
        )
    )

    assert result.channel == "text"
    assert result.delivered is False
    assert result.reason == "pc_speaker_url not configured"
    assert result.fallback_text.startswith("Water may be boiling")


def test_deliver_life_notification_posts_to_pc_speaker_url():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"ok": True})

    result = deliver_life_notification(
        LifeNotifyRequest(
            message="Water may be boiling; please confirm before adding dumplings.",
            domain="cooking",
            urgency="medium",
            requires_ack=True,
            pc_speaker_url="http://speaker.local/say",
        ),
        transport=httpx.MockTransport(handler),
    )

    assert result.channel == "pc_speaker"
    assert result.delivered is True
    assert result.reason == "delivered"
    assert result.fallback_text is None
    assert captured["url"] == "http://speaker.local/say"
    assert "please confirm" in str(captured["json"]).lower()


def test_deliver_life_notification_falls_back_when_http_delivery_fails():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "offline"})

    result = deliver_life_notification(
        LifeNotifyRequest(
            message="Water may be boiling; please confirm before adding dumplings.",
            domain="cooking",
            urgency="medium",
            pc_speaker_url="http://speaker.local/say",
        ),
        transport=httpx.MockTransport(handler),
    )

    assert result.channel == "text"
    assert result.delivered is False
    assert result.reason == "pc_speaker returned 503"
    assert result.fallback_text is not None
