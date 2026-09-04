# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""One-shot host weather refresh state-machine contracts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import cast

import pytest
from miloco.config.settings import WeatherSettings
from miloco.weather.contracts import (
    HostWeatherObservation,
    ResolvedWeatherLocation,
    WeatherCondition,
    WeatherLocationQuery,
)
from miloco.weather.service import WeatherRefreshOutcome, WeatherRefreshService
from pydantic import ValidationError


def _settings(*, enabled: bool = True) -> WeatherSettings:
    return WeatherSettings(
        enabled=enabled,
        city_name="北京市" if enabled else None,
        country_code="CN",
        refresh_interval_seconds=1_800,
        validity_seconds=3_600,
    )


def _query() -> WeatherLocationQuery:
    return WeatherLocationQuery(city_name="北京市", country_code="CN")


def _location() -> ResolvedWeatherLocation:
    return ResolvedWeatherLocation(
        city_name="北京市",
        country_code="CN",
        latitude=39.9042,
        longitude=116.4074,
        timezone="Asia/Shanghai",
    )


def _observation(
    *,
    condition: WeatherCondition = "clear",
    observed_at_ms: int = 500,
    valid_until_ms: int = 4_000_000,
) -> HostWeatherObservation:
    return HostWeatherObservation(
        condition=condition,
        observed_at_ms=observed_at_ms,
        valid_until_ms=valid_until_ms,
    )


@dataclass
class _Clock:
    value: object = 1_000
    error: Exception | None = None
    calls: int = 0

    def __call__(self) -> int:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return cast(int, self.value)


@dataclass
class _Provider:
    location: ResolvedWeatherLocation = field(default_factory=_location)
    condition: WeatherCondition = "rain"
    resolve_error: BaseException | None = None
    fetch_error: BaseException | None = None
    block_fetch: bool = False
    resolve_calls: list[WeatherLocationQuery] = field(default_factory=list)
    fetch_calls: list[ResolvedWeatherLocation] = field(default_factory=list)
    fetch_started: asyncio.Event = field(default_factory=asyncio.Event)
    fetch_release: asyncio.Event = field(default_factory=asyncio.Event)

    async def resolve_city(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation:
        self.resolve_calls.append(query)
        if self.resolve_error is not None:
            raise self.resolve_error
        return self.location

    async def fetch_current_condition(
        self,
        location: ResolvedWeatherLocation,
    ) -> WeatherCondition:
        self.fetch_calls.append(location)
        self.fetch_started.set()
        if self.block_fetch:
            await self.fetch_release.wait()
        if self.fetch_error is not None:
            raise self.fetch_error
        return self.condition


@dataclass
class _Cache:
    location: ResolvedWeatherLocation | None = None
    observation: HostWeatherObservation | None = None
    read_location_error: Exception | None = None
    write_location_error: Exception | None = None
    write_observation_error: Exception | None = None
    location_reads: list[WeatherLocationQuery] = field(default_factory=list)
    location_writes: list[tuple[WeatherLocationQuery, ResolvedWeatherLocation]] = field(
        default_factory=list
    )
    observation_reads: int = 0
    observation_writes: list[HostWeatherObservation] = field(default_factory=list)

    def read_location(
        self,
        query: WeatherLocationQuery,
    ) -> ResolvedWeatherLocation | None:
        self.location_reads.append(query)
        if self.read_location_error is not None:
            raise self.read_location_error
        return self.location

    def write_location(
        self,
        query: WeatherLocationQuery,
        location: ResolvedWeatherLocation,
    ) -> None:
        self.location_writes.append((query, location))
        if self.write_location_error is not None:
            raise self.write_location_error
        self.location = location

    def read_observation(self) -> HostWeatherObservation | None:
        self.observation_reads += 1
        return self.observation

    def write_observation(self, observation: HostWeatherObservation) -> None:
        self.observation_writes.append(observation)
        if self.write_observation_error is not None:
            raise self.write_observation_error
        self.observation = observation


def _service(
    *,
    settings: WeatherSettings | None = None,
    provider: _Provider | None = None,
    cache: _Cache | None = None,
    clock: _Clock | None = None,
) -> tuple[WeatherRefreshService, _Provider, _Cache, _Clock]:
    resolved_provider = provider or _Provider()
    resolved_cache = cache or _Cache(location=_location())
    resolved_clock = clock or _Clock()
    return (
        WeatherRefreshService(
            settings or _settings(),
            provider=resolved_provider,
            cache=resolved_cache,
            clock_ms=resolved_clock,
        ),
        resolved_provider,
        resolved_cache,
        resolved_clock,
    )


@pytest.mark.parametrize(
    "values",
    [
        {
            "status": "refreshed",
            "code": "refresh_succeeded",
            "provider_call_count": 0,
            "geocoding_call_count": 0,
        },
        {
            "status": "disabled",
            "code": "refresh_not_due",
            "provider_call_count": 0,
            "geocoding_call_count": 0,
        },
        {
            "status": "failed",
            "code": "provider_failed",
            "provider_call_count": 0,
            "geocoding_call_count": 1,
        },
        {
            "status": "failed",
            "code": "provider_failed",
            "provider_call_count": 3,
            "geocoding_call_count": 1,
        },
    ],
)
def test_outcome_rejects_status_and_call_count_mismatches(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        WeatherRefreshOutcome.model_validate(values)


@pytest.mark.asyncio
async def test_disabled_refresh_has_zero_io_including_clock() -> None:
    service, provider, cache, clock = _service(settings=_settings(enabled=False))

    outcome = await service.refresh_once()

    assert outcome == WeatherRefreshOutcome(
        status="disabled",
        code="weather_disabled",
        provider_call_count=0,
        geocoding_call_count=0,
    )
    assert clock.calls == 0
    assert cache.location_reads == []
    assert cache.location_writes == []
    assert cache.observation_writes == []
    assert provider.resolve_calls == []
    assert provider.fetch_calls == []


@pytest.mark.asyncio
async def test_cached_location_refreshes_once_with_host_timestamps() -> None:
    service, provider, cache, clock = _service()

    outcome = await service.refresh_once()

    assert outcome == WeatherRefreshOutcome(
        status="refreshed",
        code="refresh_succeeded",
        provider_call_count=1,
        geocoding_call_count=0,
    )
    assert clock.calls == 1
    assert cache.location_reads == [_query()]
    assert cache.location_writes == []
    assert provider.resolve_calls == []
    assert provider.fetch_calls == [_location()]
    assert cache.observation == _observation(
        condition="rain",
        observed_at_ms=1_000,
        valid_until_ms=3_601_000,
    )


@pytest.mark.asyncio
async def test_missing_location_geocodes_once_then_refreshes_once() -> None:
    cache = _Cache()
    service, provider, cache, _clock = _service(cache=cache)

    outcome = await service.refresh_once()

    assert outcome == WeatherRefreshOutcome(
        status="refreshed",
        code="refresh_succeeded",
        provider_call_count=2,
        geocoding_call_count=1,
    )
    assert provider.resolve_calls == [_query()]
    assert cache.location_writes == [(_query(), _location())]
    assert provider.fetch_calls == [_location()]
    assert len(cache.observation_writes) == 1


@pytest.mark.asyncio
async def test_second_attempt_inside_interval_is_not_due_after_failure() -> None:
    previous = _observation()
    provider = _Provider(fetch_error=RuntimeError("private-provider-detail"))
    cache = _Cache(location=_location(), observation=previous)
    clock = _Clock(value=10_000)
    service, provider, cache, clock = _service(
        provider=provider,
        cache=cache,
        clock=clock,
    )

    first = await service.refresh_once()
    clock.value = 11_000
    second = await service.refresh_once()

    assert first == WeatherRefreshOutcome(
        status="failed",
        code="provider_failed",
        provider_call_count=1,
        geocoding_call_count=0,
    )
    assert second == WeatherRefreshOutcome(
        status="not_due",
        code="refresh_not_due",
        provider_call_count=0,
        geocoding_call_count=0,
    )
    assert provider.fetch_calls == [_location()]
    assert cache.location_reads == [_query()]
    assert cache.observation == previous
    assert "private-provider-detail" not in repr(first)


@pytest.mark.asyncio
async def test_attempt_at_interval_boundary_refreshes_again() -> None:
    clock = _Clock(value=1_000)
    service, provider, cache, clock = _service(clock=clock)
    first = await service.refresh_once()
    clock.value = 1_801_000

    second = await service.refresh_once()

    assert first.status == "refreshed"
    assert second.status == "refreshed"
    assert len(provider.fetch_calls) == 2
    assert len(cache.observation_writes) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_now", [True, -1, 1.5, float("inf"), "1000"])
async def test_invalid_clock_fails_before_cache_or_provider_io(
    invalid_now: object,
) -> None:
    service, provider, cache, _clock = _service(clock=_Clock(value=invalid_now))

    outcome = await service.refresh_once()

    assert outcome == WeatherRefreshOutcome(
        status="failed",
        code="clock_failed",
        provider_call_count=0,
        geocoding_call_count=0,
    )
    assert cache.location_reads == []
    assert provider.resolve_calls == []
    assert provider.fetch_calls == []


@pytest.mark.asyncio
async def test_clock_exception_and_rollback_fail_without_io_or_detail() -> None:
    private_detail = "clock failed at private path"
    failed_service, provider, cache, _clock = _service(
        clock=_Clock(error=RuntimeError(private_detail))
    )

    failed = await failed_service.refresh_once()

    assert failed.code == "clock_failed"
    assert private_detail not in repr(failed)
    assert cache.location_reads == []
    assert provider.fetch_calls == []

    clock = _Clock(value=2_000)
    service, provider, cache, clock = _service(clock=clock)
    assert (await service.refresh_once()).status == "refreshed"
    clock.value = 1_999

    rolled_back = await service.refresh_once()

    assert rolled_back.code == "clock_failed"
    assert len(cache.location_reads) == 1
    assert len(provider.fetch_calls) == 1


@pytest.mark.asyncio
async def test_cache_read_failure_stops_before_provider() -> None:
    private_detail = "cache read failed at private database"
    cache = _Cache(read_location_error=RuntimeError(private_detail))
    service, provider, _cache, _clock = _service(cache=cache)

    outcome = await service.refresh_once()

    assert outcome.code == "cache_read_failed"
    assert outcome.provider_call_count == 0
    assert private_detail not in repr(outcome)
    assert provider.resolve_calls == []
    assert provider.fetch_calls == []


@pytest.mark.asyncio
async def test_cached_location_for_other_city_fails_before_forecast() -> None:
    wrong_location = ResolvedWeatherLocation(
        city_name="上海市",
        country_code="CN",
        latitude=31.2304,
        longitude=121.4737,
        timezone="Asia/Shanghai",
    )
    cache = _Cache(location=wrong_location)
    service, provider, cache, _clock = _service(cache=cache)

    outcome = await service.refresh_once()

    assert outcome.code == "cache_read_failed"
    assert outcome.provider_call_count == 0
    assert provider.fetch_calls == []
    assert cache.observation_writes == []


@pytest.mark.asyncio
async def test_geocoding_result_for_other_city_fails_before_cache_write() -> None:
    wrong_location = ResolvedWeatherLocation(
        city_name="上海市",
        country_code="CN",
        latitude=31.2304,
        longitude=121.4737,
        timezone="Asia/Shanghai",
    )
    provider = _Provider(location=wrong_location)
    cache = _Cache()
    service, provider, cache, _clock = _service(provider=provider, cache=cache)

    outcome = await service.refresh_once()

    assert outcome == WeatherRefreshOutcome(
        status="failed",
        code="provider_failed",
        provider_call_count=1,
        geocoding_call_count=1,
    )
    assert cache.location_writes == []
    assert provider.fetch_calls == []
    assert cache.observation_writes == []


@pytest.mark.asyncio
async def test_location_write_failure_stops_before_forecast() -> None:
    cache = _Cache(write_location_error=RuntimeError("private-cache-detail"))
    service, provider, _cache, _clock = _service(cache=cache)

    outcome = await service.refresh_once()

    assert outcome == WeatherRefreshOutcome(
        status="failed",
        code="cache_write_failed",
        provider_call_count=1,
        geocoding_call_count=1,
    )
    assert provider.resolve_calls == [_query()]
    assert provider.fetch_calls == []
    assert cache.observation_writes == []


@pytest.mark.asyncio
async def test_forecast_failure_preserves_previous_observation() -> None:
    previous = _observation()
    cache = _Cache(location=_location(), observation=previous)
    provider = _Provider(fetch_error=RuntimeError("private-provider-detail"))
    service, provider, cache, _clock = _service(provider=provider, cache=cache)

    outcome = await service.refresh_once()

    assert outcome.code == "provider_failed"
    assert outcome.provider_call_count == 1
    assert cache.observation == previous
    assert cache.observation_writes == []
    assert len(provider.fetch_calls) == 1


@pytest.mark.asyncio
async def test_observation_write_failure_preserves_previous_observation() -> None:
    previous = _observation()
    cache = _Cache(
        location=_location(),
        observation=previous,
        write_observation_error=RuntimeError("private-cache-detail"),
    )
    service, provider, cache, _clock = _service(cache=cache)

    outcome = await service.refresh_once()

    assert outcome.code == "cache_write_failed"
    assert outcome.provider_call_count == 1
    assert cache.observation == previous
    assert len(cache.observation_writes) == 1
    assert len(provider.fetch_calls) == 1


@pytest.mark.asyncio
async def test_concurrent_refresh_is_rejected_without_second_io() -> None:
    provider = _Provider(block_fetch=True)
    service, provider, cache, _clock = _service(provider=provider)
    first_task = asyncio.create_task(service.refresh_once())
    await provider.fetch_started.wait()

    second = await service.refresh_once()

    assert second == WeatherRefreshOutcome(
        status="busy",
        code="refresh_busy",
        provider_call_count=0,
        geocoding_call_count=0,
    )
    assert len(cache.location_reads) == 1
    assert len(provider.fetch_calls) == 1
    provider.fetch_release.set()
    assert (await first_task).status == "refreshed"


@pytest.mark.asyncio
async def test_cancellation_propagates_without_writing_observation() -> None:
    provider = _Provider(fetch_error=asyncio.CancelledError())
    clock = _Clock(value=1_000)
    service, provider, cache, clock = _service(provider=provider, clock=clock)

    with pytest.raises(asyncio.CancelledError):
        await service.refresh_once()

    assert cache.observation_writes == []
    clock.value = 2_000
    after_cancel = await service.refresh_once()
    assert after_cancel.status == "not_due"
    assert len(provider.fetch_calls) == 1
