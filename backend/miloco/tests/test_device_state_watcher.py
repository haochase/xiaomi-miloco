# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tests for the low-frequency MiOT device-state watcher."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from miloco.life.device_state_watcher import (
    DeviceStateWatcher,
    DeviceStateWatcherConfig,
    DeviceStateWatcherLoop,
    build_device_state_watcher_status,
)


class _FakeMiotService:
    def __init__(self, values: list[object]):
        self.values = list(values)
        self.calls: list[tuple[str, list[str]]] = []

    async def get_device_status(self, did: str, iids: list[str]):
        self.calls.append((did, iids))
        value = self.values.pop(0)
        if isinstance(value, Exception):
            raise value
        return {"properties": [{"iid": iids[0], "value": value, "code": 0}]}


class _FakeClock:
    def __init__(self, now_ms: int = 1_000):
        self.now_ms = now_ms

    def now(self) -> int:
        return self.now_ms

    def advance(self, ms: int) -> None:
        self.now_ms += ms


class _FakeSleeper:
    def __init__(self):
        self.calls: list[float] = []
        self.stop_after_calls = 0

    async def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        if len(self.calls) >= self.stop_after_calls:
            raise asyncio.CancelledError


def _config() -> DeviceStateWatcherConfig:
    return DeviceStateWatcherConfig(
        enabled=True,
        audit_passed=True,
        did="2119430286",
        iid="prop.2.1",
        target_value="true",
        intent="outfit_suggest",
        poll_interval_ms=30_000,
        cooldown_ms=120_000,
        error_backoff_ms=60_000,
    )


@pytest.mark.asyncio
async def test_watcher_first_poll_sets_baseline_without_triggering():
    miot = _FakeMiotService([False])
    enqueued = []
    clock = _FakeClock()
    watcher = DeviceStateWatcher(
        config=_config(),
        miot_service=miot,
        enqueue_scene_trigger=enqueued.append,
        now_ms=clock.now,
    )

    result = await watcher.poll_once()

    assert result["action"] == "baseline"
    assert result["current_value"] is False
    assert result["triggered"] is False
    assert enqueued == []
    assert miot.calls == [("2119430286", ["prop.2.1"])]


@pytest.mark.asyncio
async def test_watcher_triggers_once_on_edge_and_suppresses_held_target():
    miot = _FakeMiotService([False, True, True])
    enqueued = []
    clock = _FakeClock()
    watcher = DeviceStateWatcher(
        config=_config(),
        miot_service=miot,
        enqueue_scene_trigger=enqueued.append,
        now_ms=clock.now,
    )

    await watcher.poll_once()
    edge = await watcher.poll_once()
    held = await watcher.poll_once()

    assert edge["action"] == "triggered"
    assert edge["triggered"] is True
    assert held["action"] == "held"
    assert held["triggered"] is False
    assert len(enqueued) == 1
    payload = enqueued[0]
    assert payload.intent == "outfit_suggest"
    assert payload.trigger_source == "device_state"
    assert payload.source_id == "device_state:2119430286:prop.2.1"
    assert payload.suppress_speaker is False
    assert payload.camera_id is None


@pytest.mark.asyncio
async def test_watcher_rearms_after_value_leaves_target():
    miot = _FakeMiotService([False, True, False, True])
    enqueued = []
    clock = _FakeClock()
    watcher = DeviceStateWatcher(
        config=_config(),
        miot_service=miot,
        enqueue_scene_trigger=enqueued.append,
        now_ms=clock.now,
    )

    await watcher.poll_once()
    await watcher.poll_once()
    rearmed = await watcher.poll_once()
    clock.advance(120_000)
    second_edge = await watcher.poll_once()

    assert rearmed["action"] == "rearmed"
    assert second_edge["action"] == "triggered"
    assert len(enqueued) == 2


@pytest.mark.asyncio
async def test_watcher_uses_cooldown_and_error_backoff_without_triggering():
    miot = _FakeMiotService([False, True, False, True, RuntimeError("miot down")])
    enqueued = []
    clock = _FakeClock()
    watcher = DeviceStateWatcher(
        config=_config(),
        miot_service=miot,
        enqueue_scene_trigger=enqueued.append,
        now_ms=clock.now,
    )

    await watcher.poll_once()
    await watcher.poll_once()
    await watcher.poll_once()
    cooldown = await watcher.poll_once()
    clock.advance(120_000)
    error = await watcher.poll_once()

    assert cooldown["action"] == "cooldown"
    assert cooldown["triggered"] is False
    assert error["action"] == "error_backoff"
    assert error["triggered"] is False
    assert error["next_poll_after_ms"] == clock.now() + 60_000
    assert len(enqueued) == 1


def test_watcher_status_reports_safe_runtime_summary_without_ids():
    config = _config()
    watcher = DeviceStateWatcher(
        config=config,
        miot_service=_FakeMiotService([False]),
        enqueue_scene_trigger=[].append,
    )

    status = build_device_state_watcher_status(
        config=config,
        running=True,
        last_poll_result={"action": "baseline", "triggered": False},
        watcher=watcher,
    )

    assert status["enabled"] is True
    assert status["ready"] is True
    assert status["running"] is True
    assert status["trigger_source"] == "device_state"
    assert status["intent"] == "outfit_suggest"
    assert status["did_configured"] is True
    assert status["iid_configured"] is True
    assert status["target_value_configured"] is True
    assert status["last_poll"] == {"action": "baseline", "triggered": False}
    assert "2119430286" not in repr(status)
    assert "prop.2.1" not in repr(status)


@pytest.mark.asyncio
async def test_watcher_loop_refuses_to_start_when_safety_gates_are_missing():
    unsafe = DeviceStateWatcherConfig(
        enabled=True,
        audit_passed=False,
        did="2119430286",
        iid="prop.2.1",
        target_value="true",
        intent="outfit_suggest",
        poll_interval_ms=30_000,
        cooldown_ms=120_000,
        error_backoff_ms=60_000,
    )
    loop = DeviceStateWatcherLoop(
        config=unsafe,
        miot_service=_FakeMiotService([False]),
        enqueue_scene_trigger=[].append,
    )

    with pytest.raises(ValueError, match="missing safety/config gates"):
        await loop.start()

    assert loop.status()["running"] is False
    assert loop.status()["missing"] == ["audit_passed"]


@pytest.mark.asyncio
async def test_watcher_loop_polls_and_sleeps_until_next_poll_time():
    miot = _FakeMiotService([False, True])
    enqueued = []
    clock = _FakeClock()
    sleeper = _FakeSleeper()
    sleeper.stop_after_calls = 2
    loop = DeviceStateWatcherLoop(
        config=_config(),
        miot_service=miot,
        enqueue_scene_trigger=enqueued.append,
        now_ms=clock.now,
        sleep=sleeper.sleep,
    )

    await loop.run_forever()

    assert [call[1] for call in miot.calls] == [["prop.2.1"], ["prop.2.1"]]
    assert sleeper.calls == [30.0, 120.0]
    assert len(enqueued) == 1
    status = loop.status()
    assert status["running"] is False
    assert status["last_poll"]["action"] == "triggered"
    assert status["last_poll"]["triggered"] is True


@pytest.mark.asyncio
async def test_lifespan_helper_autostarts_watcher_and_registers_status(
    monkeypatch,
):
    from miloco.life.device_state_lifecycle import (
        _maybe_start_device_state_watcher_loop,
        _stop_device_state_watcher_loop,
    )
    from miloco.voice.router import get_device_state_watcher_loop_service

    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_WATCHER_ENABLED", "true")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_WATCHER_AUDIT_PASSED", "true")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_DID", "2119430286")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_IID", "prop.2.1")
    monkeypatch.setenv("MILOCO_LIFE_DEVICE_STATE_TARGET_VALUE", "true")

    app = SimpleNamespace(state=SimpleNamespace())
    manager = SimpleNamespace(miot_service=_FakeMiotService([False]))

    await _maybe_start_device_state_watcher_loop(app, manager)
    await asyncio.sleep(0)

    loop = get_device_state_watcher_loop_service()
    assert loop is app.state.device_state_watcher_loop
    assert loop.status()["running"] is True
    assert loop.status()["last_poll"]["action"] == "baseline"

    await _stop_device_state_watcher_loop(app)

    assert get_device_state_watcher_loop_service() is None
    assert loop.status()["running"] is False
