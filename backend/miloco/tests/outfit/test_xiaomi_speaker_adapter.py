# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Fake-contract tests for the single configured Xiaomi speaker adapter."""

from __future__ import annotations

import pytest
from miloco.outfit.xiaomi_speaker_adapter import (
    SpeakerTargetMismatchError,
    XiaomiSpeakerAdapter,
)


class _RecordingMiotSpeakerPort:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[str, ...]]] = []

    async def call_action(
        self,
        *,
        device_id: str,
        action_name: str,
        params: tuple[str, ...],
    ) -> None:
        self.calls.append((device_id, action_name, params))


class _FailingMiotSpeakerPort(_RecordingMiotSpeakerPort):
    async def call_action(
        self,
        *,
        device_id: str,
        action_name: str,
        params: tuple[str, ...],
    ) -> None:
        await super().call_action(
            device_id=device_id,
            action_name=action_name,
            params=params,
        )
        raise RuntimeError("miot unavailable")


@pytest.mark.asyncio
async def test_adapter_sends_literal_text_only_to_configured_speaker() -> None:
    port = _RecordingMiotSpeakerPort()
    adapter = XiaomiSpeakerAdapter(port, speaker_device_id="speaker-1")

    await adapter.play_text(
        device_id="speaker-1",
        text="已为你选好第一套库存穿搭。",
        idempotency_key="event-1",
    )

    assert port.calls == [("speaker-1", "play-text", ("已为你选好第一套库存穿搭。",))]


@pytest.mark.asyncio
async def test_adapter_rejects_another_speaker_before_any_miot_action() -> None:
    port = _RecordingMiotSpeakerPort()
    adapter = XiaomiSpeakerAdapter(port, speaker_device_id="speaker-1")

    with pytest.raises(SpeakerTargetMismatchError):
        await adapter.play_text(
            device_id="speaker-2",
            text="不应播放",
            idempotency_key="event-1",
        )

    assert port.calls == []


@pytest.mark.asyncio
async def test_adapter_propagates_one_miot_failure_without_retry() -> None:
    port = _FailingMiotSpeakerPort()
    adapter = XiaomiSpeakerAdapter(port, speaker_device_id="speaker-1")

    with pytest.raises(RuntimeError, match="miot unavailable"):
        await adapter.play_text(
            device_id="speaker-1",
            text="一次失败",
            idempotency_key="event-1",
        )

    assert port.calls == [("speaker-1", "play-text", ("一次失败",))]


@pytest.mark.asyncio
async def test_adapter_rejects_blank_text_before_any_miot_action() -> None:
    port = _RecordingMiotSpeakerPort()
    adapter = XiaomiSpeakerAdapter(port, speaker_device_id="speaker-1")

    with pytest.raises(ValueError, match="text"):
        await adapter.play_text(
            device_id="speaker-1",
            text=" ",
            idempotency_key="event-1",
        )

    assert port.calls == []
