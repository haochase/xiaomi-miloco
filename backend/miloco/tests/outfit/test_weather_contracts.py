# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Contracts for resolving one host-owned cached weather observation."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from miloco.outfit.filtering import WeatherRequirement
from miloco.outfit.weather_contracts import (
    CachedWeatherObservation,
    WeatherResolution,
    resolve_cached_weather,
)
from pydantic import ValidationError


@dataclass
class _CachedWeatherPort:
    observation: object = None
    error: Exception | None = None
    reads: int = 0

    def read_cached_observation(self) -> object:
        self.reads += 1
        if self.error is not None:
            raise self.error
        return self.observation


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


def test_observation_normalizes_condition_and_forbids_sensitive_fields() -> None:
    observation = CachedWeatherObservation(
        condition=" Rain ",
        observed_at_ms=1_000,
        valid_until_ms=2_000,
    )

    assert observation.condition == "rain"
    with pytest.raises(ValidationError):
        CachedWeatherObservation.model_validate(
            {
                **observation.model_dump(),
                "owner_person_id": "private-owner",
                "location": "private-location",
                "provider_response": "private-response",
            }
        )


@pytest.mark.parametrize("invalid_time", [True, -1, 1.5, float("inf"), "1000"])
def test_observation_rejects_non_epoch_millisecond_times(
    invalid_time: object,
) -> None:
    with pytest.raises(ValidationError):
        CachedWeatherObservation.model_validate(
            {
                "condition": "rain",
                "observed_at_ms": invalid_time,
                "valid_until_ms": 2_000,
            }
        )
    with pytest.raises(ValidationError):
        CachedWeatherObservation.model_validate(
            {
                "condition": "rain",
                "observed_at_ms": 1_000,
                "valid_until_ms": invalid_time,
            }
        )


def test_observation_requires_validity_after_observation() -> None:
    with pytest.raises(ValidationError):
        _observation(valid_until_ms=1_000)


@pytest.mark.parametrize("condition", ["rain", "clear"])
def test_resolver_returns_supported_available_requirement_once(condition: str) -> None:
    port = _CachedWeatherPort(observation=_observation(condition=condition))

    result = resolve_cached_weather(port, now_ms=1_500)

    assert result == WeatherResolution(
        status="available",
        requirement=WeatherRequirement(condition=condition),
    )
    assert port.reads == 1


def test_resolver_marks_missing_weather_unavailable() -> None:
    port = _CachedWeatherPort()

    result = resolve_cached_weather(port, now_ms=1_500)

    assert result == WeatherResolution(
        status="unavailable",
        error_code="weather_missing",
    )
    assert port.reads == 1


@pytest.mark.parametrize(
    ("observation", "now_ms", "error_code"),
    [
        (_observation(valid_until_ms=1_500), 1_500, "weather_stale"),
        (
            _observation(observed_at_ms=1_501, valid_until_ms=2_000),
            1_500,
            "weather_future",
        ),
        (_observation(condition="snow"), 1_500, "weather_unsupported"),
    ],
)
def test_resolver_fails_closed_for_stale_future_and_unsupported_weather(
    observation: CachedWeatherObservation,
    now_ms: int,
    error_code: str,
) -> None:
    port = _CachedWeatherPort(observation=observation)

    result = resolve_cached_weather(port, now_ms=now_ms)

    assert result.status == "unavailable"
    assert result.requirement is None
    assert result.error_code == error_code
    assert port.reads == 1


def test_resolver_hides_port_failures_and_invalid_runtime_values() -> None:
    private_detail = "provider failed at C:/private/weather.json"

    failed = resolve_cached_weather(
        _CachedWeatherPort(error=RuntimeError(private_detail)),
        now_ms=1_500,
    )
    invalid = resolve_cached_weather(
        _CachedWeatherPort(observation={"condition": private_detail}),
        now_ms=1_500,
    )

    assert failed.error_code == "weather_read_failed"
    assert invalid.error_code == "weather_read_failed"
    assert private_detail not in repr(failed)
    assert private_detail not in repr(invalid)


@pytest.mark.parametrize("invalid_now", [True, -1, 1.5, float("inf"), "1500"])
def test_resolver_rejects_invalid_now_epoch_milliseconds(
    invalid_now: object,
) -> None:
    port = _CachedWeatherPort(observation=_observation())

    with pytest.raises(ValueError, match="epoch milliseconds"):
        resolve_cached_weather(port, now_ms=invalid_now)  # type: ignore[arg-type]

    assert port.reads == 0


@pytest.mark.parametrize(
    "values",
    [
        {"status": "available"},
        {
            "status": "available",
            "requirement": {"condition": "rain"},
            "error_code": "weather_stale",
        },
        {"status": "unavailable"},
        {
            "status": "unavailable",
            "requirement": {"condition": "rain"},
            "error_code": "weather_missing",
        },
    ],
)
def test_resolution_rejects_status_payload_mismatches(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        WeatherResolution.model_validate(values)


@pytest.mark.parametrize("condition", ["snow", "Rain", "rain ", ""])
def test_available_resolution_rejects_noncanonical_conditions(
    condition: str,
) -> None:
    with pytest.raises(ValidationError):
        WeatherResolution(
            status="available",
            requirement=WeatherRequirement(condition=condition),
        )
