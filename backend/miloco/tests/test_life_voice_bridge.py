# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tests for routing detected speech into the on-demand life-agent voice bridge."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from miloco.perception.client import PerceptionEngineProxy
from miloco.perception.types import RealtimePerceptionResult, Speech


@pytest.fixture
def proxy():
    proxy = PerceptionEngineProxy.__new__(PerceptionEngineProxy)
    proxy.perception_engine = MagicMock()
    proxy._last_captions = {}
    proxy._executor = None
    return proxy


async def test_life_speech_is_consumed_by_life_voice_bridge(proxy):
    result = RealtimePerceptionResult(
        speeches=[
            Speech(
                needs_response=True,
                speaker="user",
                content=(
                    "\u5e2e\u6211\u770b\u770b"
                    "\u8fd9\u4ef6\u8863\u670d\u600e\u4e48\u642d"
                ),
                is_complete=True,
                source_device_ids=["1182348802"],
            )
        ]
    )
    manager = MagicMock()
    manager.rule_service.update_state = AsyncMock()
    manager.rule_service.get_enabled_rule_ids = MagicMock(return_value=[])

    fake_manager_module = SimpleNamespace(get_manager=MagicMock(return_value=manager))
    with patch.dict("sys.modules", {"miloco.manager": fake_manager_module}), patch(
        "miloco.perception.client.dispatch_event",
        new_callable=AsyncMock,
    ) as dispatch_event, patch(
        "miloco.perception.client.run_life_voice_turn_from_speech",
        new_callable=AsyncMock,
        return_value=True,
    ) as life_bridge:
        await proxy.handle_realtime_perception_result(result)

    life_bridge.assert_awaited_once()
    dispatch_event.assert_not_awaited()


async def test_non_life_speech_still_uses_default_dispatch(proxy):
    result = RealtimePerceptionResult(
        speeches=[
            Speech(
                needs_response=True,
                speaker="user",
                content="\u6253\u5f00\u5ba2\u5385\u706f",
                is_complete=True,
            )
        ]
    )
    manager = MagicMock()
    manager.rule_service.update_state = AsyncMock()
    manager.rule_service.get_enabled_rule_ids = MagicMock(return_value=[])

    fake_manager_module = SimpleNamespace(get_manager=MagicMock(return_value=manager))
    with patch.dict("sys.modules", {"miloco.manager": fake_manager_module}), patch(
        "miloco.perception.client.dispatch_event",
        new_callable=AsyncMock,
    ) as dispatch_event, patch(
        "miloco.perception.client.run_life_voice_turn_from_speech",
        new_callable=AsyncMock,
        return_value=False,
    ) as life_bridge:
        await proxy.handle_realtime_perception_result(result)

    life_bridge.assert_awaited_once()
    dispatch_event.assert_awaited_once()
