# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Host weather composition without real network or application startup."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from miloco.config.settings import WeatherSettings
from miloco.weather.composition import (
    HostWeatherComposition,
    WeatherCompositionError,
    build_host_weather_runtime,
)
from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherLocationQuery,
)


def _enabled_settings() -> WeatherSettings:
    return WeatherSettings(enabled=True, city_name="北京市", country_code="CN")


@dataclass
class _Runtime:
    start_error: BaseException | None = None
    stop_error: BaseException | None = None
    starts: int = 0
    stops: int = 0

    async def start(self) -> None:
        self.starts += 1
        if self.start_error is not None:
            raise self.start_error

    async def stop(self) -> None:
        self.stops += 1
        if self.stop_error is not None:
            raise self.stop_error


@dataclass
class _Transport:
    close_error: Exception | None = None
    closes: int = 0

    async def aclose(self) -> None:
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error


@dataclass
class _Cache:
    def read_location(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation | None:
        del query
        return None

    def write_location(
        self,
        query: WeatherLocationQuery,
        location: ResolvedWeatherLocation,
    ) -> None:
        del query, location
        return None

    def read_observation(self) -> HostWeatherObservation | None:
        return None

    def write_observation(self, observation: HostWeatherObservation) -> None:
        del observation
        return None


def test_disabled_build_is_lazy_and_creates_no_weather_path(tmp_path: Path) -> None:
    root = tmp_path / "disabled-host"
    code = """
import json
import sys
from pathlib import Path
from miloco.config.settings import WeatherSettings
from miloco.weather.composition import build_host_weather_runtime

root = Path(sys.argv[1])
result = build_host_weather_runtime(WeatherSettings(), root)
print(json.dumps({
    "result_is_none": result is None,
    "weather_dir_exists": (root / "weather").exists(),
    "eager_modules": sorted(
        name for name in sys.modules
        if name in {
            "miloco.weather.http_transport",
            "miloco.weather.open_meteo",
            "miloco.weather.repository",
            "miloco.weather.runtime",
            "miloco.weather.service",
        }
    ),
}))
"""
    env = os.environ.copy()
    env["MILOCO_HOME"] = str(root)

    completed = subprocess.run(
        [sys.executable, "-c", code, str(root)],
        cwd=Path(__file__).parents[2],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == {
        "result_is_none": True,
        "weather_dir_exists": False,
        "eager_modules": [],
    }


def test_enabled_build_rejects_relative_workspace_before_io(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="absolute"):
        build_host_weather_runtime(_enabled_settings(), Path("relative-workspace"))

    assert not (tmp_path / "relative-workspace").exists()


@pytest.mark.asyncio
async def test_enabled_build_creates_isolated_cache_without_starting_task(
    tmp_path: Path,
) -> None:
    pending_before = {id(task) for task in asyncio.all_tasks() if not task.done()}

    composition = build_host_weather_runtime(_enabled_settings(), tmp_path)

    assert composition is not None
    assert (tmp_path / "weather" / "weather.db").is_file()
    assert composition.cache.read_observation() is None
    pending_after = {id(task) for task in asyncio.all_tasks() if not task.done()}
    assert pending_after == pending_before
    await composition.stop()


@pytest.mark.asyncio
async def test_composition_delegates_start_and_closes_after_runtime_stop() -> None:
    events: list[str] = []

    class _OrderedRuntime(_Runtime):
        async def start(self) -> None:
            events.append("runtime_start")
            await super().start()

        async def stop(self) -> None:
            events.append("runtime_stop")
            await super().stop()

    class _OrderedTransport(_Transport):
        async def aclose(self) -> None:
            events.append("transport_close")
            await super().aclose()

    runtime = _OrderedRuntime()
    transport = _OrderedTransport()
    composition = HostWeatherComposition(
        runtime=runtime,
        cache=_Cache(),
        transport=transport,
    )

    await composition.start()
    await composition.stop()

    assert events == ["runtime_start", "runtime_stop", "transport_close"]
    assert runtime.starts == 1
    assert runtime.stops == 1
    assert transport.closes == 1


@pytest.mark.asyncio
async def test_start_failure_is_fixed_and_does_not_close_until_host_cleanup() -> None:
    private_detail = "private city and upstream response"
    runtime = _Runtime(start_error=RuntimeError(private_detail))
    transport = _Transport()
    composition = HostWeatherComposition(
        runtime=runtime,
        cache=_Cache(),
        transport=transport,
    )

    with pytest.raises(WeatherCompositionError) as exc_info:
        await composition.start()

    assert exc_info.value.code == "start_failed"
    assert private_detail not in repr(exc_info.value)
    assert transport.closes == 0
    await composition.stop()
    assert transport.closes == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["runtime", "transport"])
async def test_stop_attempts_both_resources_and_returns_fixed_failure(
    failure: str,
) -> None:
    private_detail = "private shutdown detail"
    runtime = _Runtime(
        stop_error=RuntimeError(private_detail) if failure == "runtime" else None
    )
    transport = _Transport(
        close_error=RuntimeError(private_detail) if failure == "transport" else None
    )
    composition = HostWeatherComposition(
        runtime=runtime,
        cache=_Cache(),
        transport=transport,
    )

    with pytest.raises(WeatherCompositionError) as exc_info:
        await composition.stop()

    assert exc_info.value.code == "stop_failed"
    assert private_detail not in repr(exc_info.value)
    assert runtime.stops == 1
    assert transport.closes == 1


@pytest.mark.asyncio
async def test_stop_closes_transport_before_propagating_cancellation() -> None:
    runtime = _Runtime(stop_error=asyncio.CancelledError())
    transport = _Transport()
    composition = HostWeatherComposition(
        runtime=runtime,
        cache=_Cache(),
        transport=transport,
    )

    with pytest.raises(asyncio.CancelledError):
        await composition.stop()

    assert runtime.stops == 1
    assert transport.closes == 1
