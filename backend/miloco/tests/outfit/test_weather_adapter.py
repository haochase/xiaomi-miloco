# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Fail-closed adaptation of cached weather into recommendation requirements."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest
from miloco.outfit.filtering import WeatherRequirement
from miloco.outfit.recommendation_service import WeatherRequirementPort
from miloco.outfit.weather_adapter import (
    CachedWeatherRequirementAdapter,
    WeatherUnavailableError,
)
from miloco.outfit.weather_contracts import (
    CachedWeatherObservation,
    WeatherErrorCode,
    WeatherResolution,
)


@dataclass
class _CachedWeatherPort:
    observation: CachedWeatherObservation | None = None
    error: Exception | None = None
    reads: int = 0

    def read_cached_observation(self) -> CachedWeatherObservation | None:
        self.reads += 1
        if self.error is not None:
            raise self.error
        return self.observation


@dataclass
class _Clock:
    value: object = 1_500
    error: Exception | None = None
    calls: int = 0

    def __call__(self) -> int:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return cast(int, self.value)


def _observation(
    *,
    condition: str = "rain",
    observed_at_ms: int = 1_000,
    valid_until_ms: int = 2_000,
) -> CachedWeatherObservation:
    return CachedWeatherObservation(
        condition=condition,
        observed_at_ms=observed_at_ms,
        valid_until_ms=valid_until_ms,
    )


def _as_weather_requirement_port(
    port: WeatherRequirementPort,
) -> WeatherRequirementPort:
    return port


@pytest.mark.parametrize("condition", ["rain", "clear"])
def test_adapter_returns_one_available_requirement_without_retry(
    condition: str,
) -> None:
    cache = _CachedWeatherPort(observation=_observation(condition=condition))
    clock = _Clock()
    adapter = CachedWeatherRequirementAdapter(cache, now_ms=clock)

    port = _as_weather_requirement_port(adapter)
    requirement = port.current_requirement()

    assert requirement == WeatherRequirement(condition=condition)
    assert clock.calls == 1
    assert cache.reads == 1


@pytest.mark.parametrize(
    ("observation", "error_code"),
    [
        (None, "weather_missing"),
        (_observation(valid_until_ms=1_500), "weather_stale"),
        (
            _observation(observed_at_ms=1_501, valid_until_ms=2_000),
            "weather_future",
        ),
        (_observation(condition="snow"), "weather_unsupported"),
    ],
)
def test_adapter_exposes_finite_unavailable_resolution(
    observation: CachedWeatherObservation | None,
    error_code: WeatherErrorCode,
) -> None:
    cache = _CachedWeatherPort(observation=observation)
    clock = _Clock()
    adapter = CachedWeatherRequirementAdapter(cache, now_ms=clock)

    resolution = adapter.current_resolution()

    assert resolution == WeatherResolution(
        status="unavailable",
        error_code=error_code,
    )
    assert clock.calls == 1
    assert cache.reads == 1


def test_adapter_raises_typed_failure_instead_of_returning_no_filter_fallback() -> None:
    cache = _CachedWeatherPort()
    clock = _Clock()
    adapter = CachedWeatherRequirementAdapter(cache, now_ms=clock)

    with pytest.raises(WeatherUnavailableError) as exc_info:
        adapter.current_requirement()

    assert exc_info.value.code == "weather_missing"
    assert str(exc_info.value) == "cached weather is unavailable"
    assert clock.calls == 1
    assert cache.reads == 1


@pytest.mark.parametrize("invalid_now", [True, -1, 1.5, float("inf"), "1500"])
def test_adapter_fails_closed_before_cache_read_for_invalid_clock_values(
    invalid_now: object,
) -> None:
    cache = _CachedWeatherPort(observation=_observation())
    clock = _Clock(value=invalid_now)
    adapter = CachedWeatherRequirementAdapter(cache, now_ms=clock)

    resolution = adapter.current_resolution()

    assert resolution == WeatherResolution(
        status="unavailable",
        error_code="weather_read_failed",
    )
    assert clock.calls == 1
    assert cache.reads == 0


def test_adapter_hides_clock_and_cache_failure_details_without_retry() -> None:
    private_detail = "weather failed at E:/private/location.json"
    clock = _Clock(error=RuntimeError(private_detail))
    clock_cache = _CachedWeatherPort(observation=_observation())
    clock_adapter = CachedWeatherRequirementAdapter(clock_cache, now_ms=clock)

    clock_resolution = clock_adapter.current_resolution()

    assert clock_resolution.error_code == "weather_read_failed"
    assert private_detail not in repr(clock_resolution)
    assert clock.calls == 1
    assert clock_cache.reads == 0

    cache = _CachedWeatherPort(error=RuntimeError(private_detail))
    cache_clock = _Clock()
    cache_adapter = CachedWeatherRequirementAdapter(cache, now_ms=cache_clock)

    with pytest.raises(WeatherUnavailableError) as exc_info:
        cache_adapter.current_requirement()

    assert exc_info.value.code == "weather_read_failed"
    assert private_detail not in str(exc_info.value)
    assert private_detail not in repr(exc_info.value)
    assert cache_clock.calls == 1
    assert cache.reads == 1
