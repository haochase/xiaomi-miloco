# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Bounded HTTP transport tests using only httpx.MockTransport."""

from __future__ import annotations

from typing import Any, cast

import httpx
import pytest
from miloco.weather.http_transport import HttpxWeatherTransport, WeatherTransportError
from miloco.weather.open_meteo import FORECAST_URL, GEOCODING_URL


def _json_response(payload: object, *, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers={"Content-Type": "application/json; charset=utf-8"},
        json=payload,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [GEOCODING_URL, FORECAST_URL])
async def test_transport_gets_allowed_endpoint_without_credentials(url: str) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _json_response({"ok": True})

    transport = HttpxWeatherTransport(transport=httpx.MockTransport(handler))
    try:
        result = await transport.get_json(
            url=url,
            params={"name": "北京市", "countryCode": "CN"},
            timeout_seconds=5.0,
        )
    finally:
        await transport.aclose()

    assert result == {"ok": True}
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "GET"
    assert str(request.url.copy_with(query=None)) == url
    assert dict(request.url.params) == {"name": "北京市", "countryCode": "CN"}
    assert request.headers["accept"] == "application/json"
    assert "authorization" not in request.headers
    assert "x-api-key" not in request.headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://api.open-meteo.com/v1/forecast",
        "https://private.invalid/v1/forecast",
        "https://api.open-meteo.com/v1/private",
        "https://geocoding-api.open-meteo.com/v1/private",
    ],
)
async def test_transport_rejects_non_allowlisted_url_before_io(url: str) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _json_response({})

    transport = HttpxWeatherTransport(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(WeatherTransportError) as exc_info:
            await transport.get_json(
                url=url,
                params={"current": "weather_code"},
                timeout_seconds=5.0,
            )
    finally:
        await transport.aclose()

    assert exc_info.value.code == "invalid_request"
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"": "value"},
        {"apikey": "private-secret"},
        {"Authorization": "private-secret"},
        {f"p{index}": "v" for index in range(9)},
        cast(dict[str, str], {"name": 1}),
        {"name": ""},
    ],
)
async def test_transport_rejects_unsafe_params_before_io(
    params: dict[str, str],
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _json_response({})

    transport = HttpxWeatherTransport(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(WeatherTransportError) as exc_info:
            await transport.get_json(
                url=FORECAST_URL,
                params=params,
                timeout_seconds=5.0,
            )
    finally:
        await transport.aclose()

    assert exc_info.value.code == "invalid_request"
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("timeout_seconds", [True, 0, -1, 30.1, float("inf"), "5"])
async def test_transport_rejects_invalid_timeout_before_io(
    timeout_seconds: Any,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _json_response({})

    transport = HttpxWeatherTransport(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(WeatherTransportError) as exc_info:
            await transport.get_json(
                url=FORECAST_URL,
                params={"current": "weather_code"},
                timeout_seconds=timeout_seconds,
            )
    finally:
        await transport.aclose()

    assert exc_info.value.code == "invalid_request"
    assert calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [301, 302, 307, 400, 429, 500])
async def test_transport_transport_does_not_follow_redirects_or_reflect_http_body(
    status_code: int,
) -> None:
    calls = 0
    private_detail = "private upstream body with coordinates and credential"

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status_code,
            headers={
                "Location": "https://private.invalid/redirect",
                "Content-Type": "text/plain",
            },
            text=private_detail,
        )

    transport = HttpxWeatherTransport(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(WeatherTransportError) as exc_info:
            await transport.get_json(
                url=FORECAST_URL,
                params={"current": "weather_code"},
                timeout_seconds=5.0,
            )
    finally:
        await transport.aclose()

    assert exc_info.value.code == "request_failed"
    assert private_detail not in repr(exc_info.value)
    assert calls == 1


@pytest.mark.asyncio
async def test_transport_rejects_non_json_content_type() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Content-Type": "text/html"}, text="{}")

    transport = HttpxWeatherTransport(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(WeatherTransportError) as exc_info:
            await transport.get_json(
                url=FORECAST_URL,
                params={"current": "weather_code"},
                timeout_seconds=5.0,
            )
    finally:
        await transport.aclose()

    assert exc_info.value.code == "response_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize("content", [b"not-json", b"\xff\xfe"])
async def test_transport_rejects_invalid_json_without_reflection(
    content: bytes,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=content,
        )

    transport = HttpxWeatherTransport(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(WeatherTransportError) as exc_info:
            await transport.get_json(
                url=FORECAST_URL,
                params={"current": "weather_code"},
                timeout_seconds=5.0,
            )
    finally:
        await transport.aclose()

    assert exc_info.value.code == "response_invalid"
    assert content.hex() not in repr(exc_info.value)


@pytest.mark.asyncio
async def test_transport_rejects_decoded_response_over_byte_limit() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return _json_response({"private": "x" * 256})

    transport = HttpxWeatherTransport(
        transport=httpx.MockTransport(handler),
        max_response_bytes=64,
    )
    try:
        with pytest.raises(WeatherTransportError) as exc_info:
            await transport.get_json(
                url=FORECAST_URL,
                params={"current": "weather_code"},
                timeout_seconds=5.0,
            )
    finally:
        await transport.aclose()

    assert exc_info.value.code == "response_too_large"


@pytest.mark.asyncio
async def test_closed_transport_fails_before_io_and_close_is_idempotent() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return _json_response({})

    transport = HttpxWeatherTransport(transport=httpx.MockTransport(handler))
    await transport.aclose()
    await transport.aclose()

    with pytest.raises(WeatherTransportError) as exc_info:
        await transport.get_json(
            url=FORECAST_URL,
            params={"current": "weather_code"},
            timeout_seconds=5.0,
        )

    assert exc_info.value.code == "transport_closed"
    assert calls == 0


@pytest.mark.parametrize(
    "max_response_bytes",
    [True, 0, -1, 1.5, float("inf"), "65536", 1_048_577],
)
def test_transport_rejects_invalid_response_limit(max_response_bytes: Any) -> None:
    with pytest.raises(ValueError, match="response byte limit"):
        HttpxWeatherTransport(
            transport=httpx.MockTransport(lambda _request: _json_response({})),
            max_response_bytes=max_response_bytes,
        )
