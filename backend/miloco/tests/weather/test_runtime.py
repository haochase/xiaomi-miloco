# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Host weather background lifecycle with deterministic fake sleep."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from miloco.weather.runtime import HostWeatherRuntime


@dataclass
class _RefreshService:
    error: Exception | None = None
    calls: int = 0
    call_events: asyncio.Queue[int] = field(default_factory=asyncio.Queue)

    async def refresh_once(self) -> object:
        self.calls += 1
        await self.call_events.put(self.calls)
        if self.error is not None:
            raise self.error
        return object()


@dataclass
class _ControlledSleep:
    calls: list[float] = field(default_factory=list)
    entered: asyncio.Queue[asyncio.Event] = field(default_factory=asyncio.Queue)

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        release = asyncio.Event()
        await self.entered.put(release)
        await release.wait()


@pytest.mark.asyncio
async def test_start_refreshes_once_then_sleeps_and_is_idempotent() -> None:
    service = _RefreshService()
    sleep = _ControlledSleep()
    runtime = HostWeatherRuntime(
        service,
        interval_seconds=1_800,
        sleep=sleep,
    )

    await runtime.start()
    assert await service.call_events.get() == 1
    first_release = await sleep.entered.get()
    await runtime.start()

    assert service.calls == 1
    assert sleep.calls == [1_800.0]
    first_release.set()
    assert await service.call_events.get() == 2
    await asyncio.wait_for(runtime.stop(), timeout=1.0)


@pytest.mark.asyncio
async def test_refresh_failure_logs_fixed_code_and_waits_before_next_attempt(
    caplog: pytest.LogCaptureFixture,
) -> None:
    private_detail = "private provider response and coordinates"
    service = _RefreshService(error=RuntimeError(private_detail))
    sleep = _ControlledSleep()
    runtime = HostWeatherRuntime(service, interval_seconds=1_800, sleep=sleep)

    await runtime.start()
    assert await service.call_events.get() == 1
    _release = await sleep.entered.get()

    assert service.calls == 1
    assert sleep.calls == [1_800.0]
    assert "weather_refresh_failed" in caplog.text
    assert private_detail not in caplog.text
    await asyncio.wait_for(runtime.stop(), timeout=1.0)


@pytest.mark.asyncio
async def test_each_period_waits_before_refreshing_again() -> None:
    service = _RefreshService()
    sleep = _ControlledSleep()
    runtime = HostWeatherRuntime(service, interval_seconds=1_800, sleep=sleep)
    await runtime.start()
    assert await service.call_events.get() == 1
    first_release = await sleep.entered.get()

    first_release.set()
    assert await service.call_events.get() == 2
    second_release = await sleep.entered.get()

    assert sleep.calls == [1_800.0, 1_800.0]
    assert service.calls == 2
    second_release.set()
    assert await service.call_events.get() == 3
    await asyncio.wait_for(runtime.stop(), timeout=1.0)


@pytest.mark.asyncio
async def test_stop_before_start_and_repeated_stop_are_noops() -> None:
    service = _RefreshService()
    sleep = _ControlledSleep()
    runtime = HostWeatherRuntime(service, interval_seconds=1_800, sleep=sleep)

    await runtime.stop()
    await runtime.stop()
    await runtime.start()

    assert service.calls == 0
    assert sleep.calls == []


@pytest.mark.asyncio
async def test_stop_cancels_wait_without_extra_refresh() -> None:
    service = _RefreshService()
    sleep = _ControlledSleep()
    runtime = HostWeatherRuntime(service, interval_seconds=1_800, sleep=sleep)
    await runtime.start()
    assert await service.call_events.get() == 1
    await sleep.entered.get()

    await asyncio.wait_for(runtime.stop(), timeout=1.0)

    assert service.calls == 1
    assert sleep.calls == [1_800.0]


@pytest.mark.parametrize(
    "interval_seconds",
    [True, 0, -1, 299, 86_401, 1.5, float("inf"), "1800"],
)
def test_runtime_rejects_invalid_interval(interval_seconds: Any) -> None:
    with pytest.raises(ValueError, match="interval"):
        HostWeatherRuntime(
            _RefreshService(),
            interval_seconds=interval_seconds,
            sleep=_ControlledSleep(),
        )
