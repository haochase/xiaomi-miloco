# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tests for low-sensitivity Outfit moment notification adaptation."""

import pytest
from miloco.life.outfit_moment_notification import (
    OutfitMomentNotificationDispatcher,
    build_outfit_moment_notification,
)
from miloco.life.outfit_moments import OutfitMoment, OutfitMomentTag


class FakeNotificationPort:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages = []

    async def send_outfit_moment_notification(self, message) -> None:
        if self.fail:
            raise RuntimeError("transport unavailable")
        self.messages.append(message)


def _moment() -> OutfitMoment:
    return OutfitMoment(
        moment_id="moment-1",
        owner_person_id="owner-1",
        occurred_at_ms=1000,
        timezone="Asia/Shanghai",
        recommendation_id="recommendation-1",
        confirmed_wear_event_id="wear-1",
        item_ids=("top-1", "bottom-1"),
        source_event_ids=("wear-1",),
        created_at_ms=1001,
    )


def _tag(review_status: str = "confirmed") -> OutfitMomentTag:
    return OutfitMomentTag(
        tag_id="tag-1",
        moment_id="moment-1",
        tag_type="repeat_favorite",
        label="Favorite combination",
        narrative="A user-approved note.",
        evidence_signal_ids=("signal-1",),
        source="rule",
        confidence=0.9,
        review_status=review_status,
        dedupe_key="repeat:moment-1",
        generator_version="rule-v1",
    )


def test_notification_never_includes_private_fields_and_uses_a_safe_deep_link() -> None:
    notification = build_outfit_moment_notification(
        _moment(), _tag(), panel_base_url="https://panel.example.test"
    )

    assert notification.summary == "A confirmed outfit moment is ready to review."
    assert notification.deep_link_path == "/#/agents/outfit/moments/moment-1"
    assert (
        notification.panel_url
        == "https://panel.example.test/#/agents/outfit/moments/moment-1"
    )
    assert "owner-1" not in notification.summary
    assert "tag-1" not in notification.summary
    assert "Favorite combination" not in notification.summary
    assert notification.idempotency_key.startswith("outfit-moment-v1:")


def test_notification_without_public_base_degrades_to_summary_only() -> None:
    notification = build_outfit_moment_notification(_moment(), _tag())

    assert notification.panel_url is None
    assert notification.deep_link_path == "/#/agents/outfit/moments/moment-1"


@pytest.mark.asyncio
async def test_dispatcher_is_idempotent_and_keeps_failed_attempts_retryable() -> None:
    port = FakeNotificationPort()
    dispatcher = OutfitMomentNotificationDispatcher(port)
    notification = build_outfit_moment_notification(_moment(), _tag())

    assert await dispatcher.dispatch(notification) is True
    assert await dispatcher.dispatch(notification) is False
    assert port.messages == [notification]

    failing_port = FakeNotificationPort(fail=True)
    retryable_dispatcher = OutfitMomentNotificationDispatcher(failing_port)
    with pytest.raises(RuntimeError, match="transport unavailable"):
        await retryable_dispatcher.dispatch(notification)
    failing_port.fail = False

    assert await retryable_dispatcher.dispatch(notification) is True
    assert failing_port.messages == [notification]


def test_only_user_approved_tags_can_trigger_notifications() -> None:
    with pytest.raises(ValueError, match="approved tag"):
        build_outfit_moment_notification(_moment(), _tag("pending"))


@pytest.mark.parametrize(
    "panel_base_url",
    [
        "ftp://panel.example.test",
        "https://user:secret@panel.example.test",
        "https://panel.example.test/control",
        "https://panel.example.test/?token=secret",
    ],
)
def test_notification_rejects_unsafe_panel_base_urls(panel_base_url: str) -> None:
    with pytest.raises(ValueError, match="panel base URL"):
        build_outfit_moment_notification(
            _moment(), _tag(), panel_base_url=panel_base_url
        )
