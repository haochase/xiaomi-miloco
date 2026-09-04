# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Pure host weather facts and provider/cache boundaries."""

from __future__ import annotations

import math
import re
from typing import Literal, Protocol, Self, TypeAlias
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictFloat,
    StrictInt,
    field_validator,
    model_validator,
)

WeatherCondition: TypeAlias = Literal["rain", "clear"]
_COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")


def _normalize_city_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("city_name must not be blank")
    return value.strip()


def _normalize_country_code(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("country_code must be a string")
    normalized = value.strip().upper()
    if _COUNTRY_CODE.fullmatch(normalized) is None:
        raise ValueError("country_code must be ISO alpha-2")
    return normalized


def _require_epoch_milliseconds(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("epoch milliseconds must be a non-negative integer")
    return value


class WeatherLocationQuery(BaseModel):
    """One configured city identity without provider or owner selectors."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    city_name: str
    country_code: str

    _normalize_city = field_validator("city_name", mode="before")(_normalize_city_name)
    _normalize_country = field_validator("country_code", mode="before")(
        _normalize_country_code
    )


class ResolvedWeatherLocation(BaseModel):
    """A bounded WGS84 location cached only by the host."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    city_name: str
    country_code: str
    latitude: StrictFloat
    longitude: StrictFloat
    timezone: str

    _normalize_city = field_validator("city_name", mode="before")(_normalize_city_name)
    _normalize_country = field_validator("country_code", mode="before")(
        _normalize_country_code
    )

    @field_validator("latitude", "longitude")
    @classmethod
    def validate_coordinate(cls, value: float, info) -> float:
        if not math.isfinite(value):
            raise ValueError("weather coordinates must be finite")
        minimum, maximum = (
            (-90.0, 90.0) if info.field_name == "latitude" else (-180.0, 180.0)
        )
        if not minimum <= value <= maximum:
            raise ValueError("weather coordinate is outside WGS84 bounds")
        return value

    @field_validator("timezone", mode="before")
    @classmethod
    def validate_timezone(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("weather timezone must not be blank")
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("weather timezone must be a valid IANA name") from error
        return normalized


class HostWeatherObservation(BaseModel):
    """One finite weather fact without location or provider details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    condition: WeatherCondition
    observed_at_ms: StrictInt
    valid_until_ms: StrictInt

    @field_validator("observed_at_ms", "valid_until_ms")
    @classmethod
    def validate_epoch_milliseconds(cls, value: int) -> int:
        return _require_epoch_milliseconds(value)

    @model_validator(mode="after")
    def validate_validity_window(self) -> Self:
        if self.valid_until_ms <= self.observed_at_ms:
            raise ValueError("weather validity must end after observation")
        return self


class WeatherProviderPort(Protocol):
    """Resolve and fetch through an injected provider implementation."""

    async def resolve_city(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation: ...

    async def fetch_current_condition(
        self,
        location: ResolvedWeatherLocation,
    ) -> WeatherCondition: ...


class WeatherCachePort(Protocol):
    """Read and write host-owned normalized weather cache facts."""

    def read_location(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation | None: ...

    def write_location(
        self,
        query: WeatherLocationQuery,
        location: ResolvedWeatherLocation,
    ) -> None: ...

    def read_observation(self) -> HostWeatherObservation | None: ...

    def write_observation(self, observation: HostWeatherObservation) -> None: ...
