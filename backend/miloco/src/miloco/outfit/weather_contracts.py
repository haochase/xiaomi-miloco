# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Fail-closed contracts for one host-owned cached weather observation."""

from __future__ import annotations

from typing import Literal, Protocol, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, StrictInt, field_validator, model_validator

from miloco.outfit.filtering import WeatherRequirement

WeatherResolutionStatus: TypeAlias = Literal["available", "unavailable"]
WeatherErrorCode: TypeAlias = Literal[
    "weather_missing",
    "weather_stale",
    "weather_future",
    "weather_unsupported",
    "weather_read_failed",
]
_SUPPORTED_CONDITIONS = frozenset({"rain", "clear"})


def _require_epoch_milliseconds(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("epoch milliseconds must be a non-negative integer")
    return value


class CachedWeatherObservation(BaseModel):
    """A normalized cached fact without owner, location, or provider details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: str
    observed_at_ms: StrictInt
    valid_until_ms: StrictInt

    @field_validator("condition", mode="before")
    @classmethod
    def normalize_condition(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("weather condition must not be blank")
        return value.strip().lower()

    @field_validator("observed_at_ms", "valid_until_ms")
    @classmethod
    def validate_epoch_milliseconds(cls, value: int) -> int:
        return _require_epoch_milliseconds(value)

    @model_validator(mode="after")
    def validate_validity_window(self) -> Self:
        if self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("weather validity must end after observation")
        return self


class CachedWeatherPort(Protocol):
    """Host-owned cache read; implementations must not trigger a remote fetch."""

    def read_cached_observation(self) -> CachedWeatherObservation | None: ...


class WeatherResolution(BaseModel):
    """Either one supported requirement or one fixed unavailable reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: WeatherResolutionStatus
    requirement: WeatherRequirement | None = None
    error_code: WeatherErrorCode | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        if self.status == "available":
            if self.requirement is None or self.error_code is not None:
                raise ValueError(
                    "available weather requires a requirement and no error code"
                )
            if self.requirement.condition not in _SUPPORTED_CONDITIONS:
                raise ValueError(
                    "available weather requires a supported canonical condition"
                )
            return self
        if self.requirement is not None or self.error_code is None:
            raise ValueError(
                "unavailable weather requires an error code and no requirement"
            )
        return self


def resolve_cached_weather(
    port: CachedWeatherPort,
    *,
    now_ms: int,
) -> WeatherResolution:
    """Resolve one cached read without fetching, retrying, or reflecting failures."""

    now = _require_epoch_milliseconds(now_ms)
    try:
        observation = port.read_cached_observation()
    except Exception:
        return _unavailable("weather_read_failed")

    if observation is None:
        return _unavailable("weather_missing")
    if not isinstance(observation, CachedWeatherObservation):
        return _unavailable("weather_read_failed")
    if observation.observed_at_ms > now:
        return _unavailable("weather_future")
    if observation.valid_until_ms <= now:
        return _unavailable("weather_stale")
    if observation.condition not in _SUPPORTED_CONDITIONS:
        return _unavailable("weather_unsupported")
    return WeatherResolution(
        status="available",
        requirement=WeatherRequirement(condition=observation.condition),
    )


def _unavailable(error_code: WeatherErrorCode) -> WeatherResolution:
    return WeatherResolution(status="unavailable", error_code=error_code)
