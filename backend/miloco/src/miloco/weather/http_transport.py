# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Bounded HTTP JSON transport for fixed Open-Meteo endpoints."""

from __future__ import annotations

import json
import math
from typing import Literal, TypeAlias

import httpx

from miloco.weather.open_meteo import FORECAST_URL, GEOCODING_URL

WeatherTransportErrorCode: TypeAlias = Literal[
    "invalid_request",
    "request_failed",
    "response_invalid",
    "response_too_large",
    "transport_closed",
]
_ALLOWED_URLS = frozenset({GEOCODING_URL, FORECAST_URL})
_SENSITIVE_PARAM_NAMES = frozenset(
    {"api_key", "apikey", "authorization", "key", "secret", "token"}
)


class WeatherTransportError(RuntimeError):
    """Finite transport failure without URL, payload, or exception details."""

    def __init__(self, code: WeatherTransportErrorCode) -> None:
        self.code = code
        super().__init__("weather transport unavailable")


class HttpxWeatherTransport:
    """Own one bounded client restricted to the two reviewed weather endpoints."""

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        max_response_bytes: int = 65_536,
    ) -> None:
        self._max_response_bytes = _require_response_limit(max_response_bytes)
        self._client = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            headers={"Accept": "application/json"},
            limits=httpx.Limits(max_connections=2, max_keepalive_connections=1),
            trust_env=False,
        )
        self._closed = False

    async def get_json(
        self,
        *,
        url: str,
        params: dict[str, str],
        timeout_seconds: float,
    ) -> object:
        """GET and decode one bounded JSON response without following redirects."""

        if self._closed:
            raise WeatherTransportError("transport_closed")
        if url not in _ALLOWED_URLS or not _valid_params(params):
            raise WeatherTransportError("invalid_request")
        timeout = _httpx_timeout(timeout_seconds)

        try:
            async with self._client.stream(
                "GET",
                url,
                params=params,
                timeout=timeout,
            ) as response:
                if not 200 <= response.status_code < 300:
                    raise WeatherTransportError("request_failed")
                content_type = response.headers.get("Content-Type", "")
                if content_type.split(";", 1)[0].strip().lower() != "application/json":
                    raise WeatherTransportError("response_invalid")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > self._max_response_bytes:
                        raise WeatherTransportError("response_too_large")
        except WeatherTransportError:
            raise
        except Exception:
            raise WeatherTransportError("request_failed") from None

        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise WeatherTransportError("response_invalid") from None

    async def aclose(self) -> None:
        """Close the owned client once."""

        if self._closed:
            return
        self._closed = True
        await self._client.aclose()


def _valid_params(params: object) -> bool:
    if not isinstance(params, dict) or not 1 <= len(params) <= 8:
        return False
    total_length = 0
    for key, value in params.items():
        if not isinstance(key, str) or not isinstance(value, str):
            return False
        if not key or not value or key.casefold() in _SENSITIVE_PARAM_NAMES:
            return False
        if len(key) > 64 or len(value) > 512:
            return False
        total_length += len(key) + len(value)
    return total_length <= 2_048


def _httpx_timeout(value: object) -> httpx.Timeout:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WeatherTransportError("invalid_request")
    seconds = float(value)
    if not math.isfinite(seconds) or not 0 < seconds <= 30:
        raise WeatherTransportError("invalid_request")
    bounded_connect_pool = min(seconds, 5.0)
    return httpx.Timeout(
        connect=bounded_connect_pool,
        read=seconds,
        write=seconds,
        pool=bounded_connect_pool,
    )


def _require_response_limit(value: object) -> int:
    if type(value) is not int or not 1 <= value <= 1_048_576:
        raise ValueError("weather response byte limit must be within one MiB")
    return value
