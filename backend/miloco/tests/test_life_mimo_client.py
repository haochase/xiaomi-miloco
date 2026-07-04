# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Tests for the Life Agent scoped MiMo client."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any


async def test_life_mimo_audio_call_uses_asr_v25_and_completion_tokens(
    monkeypatch,
):
    from miloco.life import mimo_client

    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        text = "{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {"message": {"content": '{"transcript":"帮我看看这件衣服"}'}}
                ],
                "usage": {},
            }

    class _Client:
        def __init__(self, *, timeout: float):
            captured["timeout"] = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> _Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(mimo_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        mimo_client,
        "get_settings",
        lambda: SimpleNamespace(
            model=SimpleNamespace(
                omni=SimpleNamespace(
                    model="mimo-v2-omni",
                    base_url="https://token-plan-cn.xiaomimimo.com/v1",
                    api_key="test-key",
                )
            )
        ),
    )

    raw = await mimo_client.call_life_mimo_chat(
        system_prompt="只转写",
        user_content="转写音频",
        audio_base64="ZmFrZQ==",
        task="asr",
        max_completion_tokens=180,
    )

    assert raw["choices"][0]["message"]["content"]
    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    assert captured["headers"]["api-key"] == "test-key"
    assert "Authorization" not in captured["headers"]
    body = captured["json"]
    assert body["model"] == "mimo-v2.5-asr"
    assert body["max_completion_tokens"] == 180
    assert "max_tokens" not in body
    assert body["thinking"] == {"type": "disabled"}
    assert body["asr_options"] == {"language": "auto"}
    assert body["messages"] == [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_audio",
                    "input_audio": {"data": "data:audio/wav;base64,ZmFrZQ=="},
                }
            ],
        }
    ]


def test_life_mimo_audio_call_uses_bearer_for_standard_mimo_host(
    monkeypatch,
):
    from miloco.life import mimo_client

    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        text = "{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    class _Client:
        def __init__(self, *, timeout: float):
            captured["timeout"] = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> _Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(mimo_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        mimo_client,
        "get_settings",
        lambda: SimpleNamespace(
            model=SimpleNamespace(
                omni=SimpleNamespace(
                    model="mimo-v2.5",
                    base_url="https://api.xiaomimimo.com/v1",
                    api_key="sk-test",
                )
            )
        ),
    )

    asyncio.run(
        mimo_client.call_life_mimo_chat(
            system_prompt="只转写",
            user_content="转写音频",
            audio_base64="ZmFrZQ==",
            task="asr",
            max_completion_tokens=180,
        )
    )

    assert captured["url"] == "https://api.xiaomimimo.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert "api-key" not in captured["headers"]


async def test_life_mimo_http_error_includes_sanitized_candidate_context(
    monkeypatch,
):
    import httpx
    from miloco.life import mimo_client
    from miloco.perception.engine.omni.omni_client import OmniError

    request = httpx.Request(
        "POST",
        "https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
    )
    response = httpx.Response(
        404,
        text='{"error":"model route not found for secret-key"}',
        request=request,
    )

    class _Client:
        def __init__(self, *, timeout: float):
            self.timeout = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> httpx.Response:
            return response

    monkeypatch.setattr(mimo_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        mimo_client,
        "get_settings",
        lambda: SimpleNamespace(
            model=SimpleNamespace(
                omni=SimpleNamespace(
                    model="mimo-v2-omni",
                    base_url="https://token-plan-cn.xiaomimimo.com/v1",
                    api_key="secret-key",
                )
            )
        ),
    )

    try:
        await mimo_client.call_life_mimo_chat(
            system_prompt="asr",
            user_content="transcribe",
            audio_base64="ZmFrZQ==",
            task="asr",
            max_completion_tokens=180,
        )
    except OmniError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected OmniError")

    assert "HTTP 404" in message
    assert "task=asr" in message
    assert "model=mimo-v2.5-asr" in message
    assert "base_url=https://token-plan-cn.xiaomimimo.com/v1" in message
    assert "path=/v1/chat/completions" in message
    assert "response_excerpt=" in message
    assert "secret-key" not in message


async def test_life_mimo_http_error_includes_sanitized_request_shape(
    monkeypatch,
):
    import httpx
    from miloco.life import mimo_client
    from miloco.perception.engine.omni.omni_client import OmniError

    request = httpx.Request(
        "POST",
        "https://api.xiaomimimo.com/v1/chat/completions",
    )
    response = httpx.Response(
        400,
        text='{"error":"bad request for secret-key"}',
        request=request,
    )

    class _Client:
        def __init__(self, *, timeout: float):
            self.timeout = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> httpx.Response:
            return response

    monkeypatch.setattr(mimo_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        mimo_client,
        "get_settings",
        lambda: SimpleNamespace(
            model=SimpleNamespace(
                omni=SimpleNamespace(
                    model="mimo-v2-omni",
                    base_url="https://api.xiaomimimo.com/v1",
                    api_key="secret-key",
                )
            )
        ),
    )

    try:
        await mimo_client.call_life_mimo_chat(
            system_prompt="vision",
            user_content="describe",
            video_base64="dmlkZW8tc2VjcmV0LWJhc2U2NA==",
            task="vision",
            max_completion_tokens=900,
        )
    except OmniError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected OmniError")

    assert "HTTP 400" in message
    assert "request_shape=" in message
    assert "message_roles=system,user" in message
    assert "modalities=text,video_url" in message
    assert "max_completion_tokens=900" in message
    assert "thinking=disabled" in message
    assert "dmlkZW8tc2VjcmV0LWJhc2U2NA==" not in message
    assert "secret-key" not in message


async def test_life_mimo_visual_call_uses_v25_video_request_shape(monkeypatch):
    from miloco.life import mimo_client

    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        text = "{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    class _Client:
        def __init__(self, *, timeout: float):
            captured["timeout"] = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> _Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(mimo_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        mimo_client,
        "get_settings",
        lambda: SimpleNamespace(
            model=SimpleNamespace(
                omni=SimpleNamespace(
                    model="mimo-v2-omni",
                    base_url="https://token-plan-cn.xiaomimimo.com/v1",
                    api_key="test-key",
                )
            )
        ),
    )

    await mimo_client.call_life_mimo_chat(
        system_prompt="抽取",
        user_content="识别画面",
        video_base64="ZmFrZQ==",
        task="vision",
        max_completion_tokens=900,
    )

    body = captured["json"]
    assert body["model"] == "mimo-v2.5"
    assert body["max_completion_tokens"] == 900
    assert "max_tokens" not in body
    assert body["thinking"] == {"type": "disabled"}
    assert body["messages"][1]["content"] == [
        {
            "type": "video_url",
            "video_url": {"url": "data:video/mp4;base64,ZmFrZQ=="},
            "fps": 2,
            "media_resolution": "default",
        },
        {"type": "text", "text": "识别画面"},
    ]


async def test_life_mimo_image_call_uses_v25_image_request_shape(monkeypatch):
    from miloco.life import mimo_client

    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        text = "{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    class _Client:
        def __init__(self, *, timeout: float):
            captured["timeout"] = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> _Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(mimo_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        mimo_client,
        "get_settings",
        lambda: SimpleNamespace(
            model=SimpleNamespace(
                omni=SimpleNamespace(
                    model="mimo-v2-omni",
                    base_url="",
                    api_key="test-key",
                )
            )
        ),
    )

    await mimo_client.call_life_mimo_chat(
        system_prompt="抽取",
        user_content="识别图片",
        image_base64="ZmFrZQ==",
        image_mime_type="image/png",
        task="vision",
        max_completion_tokens=900,
    )

    body = captured["json"]
    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    assert body["model"] == "mimo-v2.5"
    assert body["thinking"] == {"type": "disabled"}
    assert body["messages"][1]["content"] == [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,ZmFrZQ=="},
        },
        {"type": "text", "text": "识别图片"},
    ]


async def test_life_mimo_audio_understanding_uses_v25_audio_request_shape(
    monkeypatch,
):
    from miloco.life import mimo_client

    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200
        text = "{}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    class _Client:
        def __init__(self, *, timeout: float):
            captured["timeout"] = timeout

        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> _Response:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Response()

    monkeypatch.setattr(mimo_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(
        mimo_client,
        "get_settings",
        lambda: SimpleNamespace(
            model=SimpleNamespace(
                omni=SimpleNamespace(
                    model="mimo-v2-omni",
                    base_url="https://token-plan-cn.xiaomimimo.com/v1",
                    api_key="test-key",
                )
            )
        ),
    )

    await mimo_client.call_life_mimo_chat(
        system_prompt="理解音频",
        user_content="描述音频内容",
        audio_base64="ZmFrZQ==",
        audio_mime_type="audio/wav",
        task="audio",
        max_completion_tokens=900,
    )

    body = captured["json"]
    assert body["model"] == "mimo-v2.5"
    assert body["thinking"] == {"type": "disabled"}
    assert "asr_options" not in body
    assert body["messages"][1]["content"] == [
        {
            "type": "input_audio",
            "input_audio": {"data": "data:audio/wav;base64,ZmFrZQ=="},
        },
        {"type": "text", "text": "描述音频内容"},
    ]


def test_life_mimo_model_env_override(monkeypatch):
    from miloco.life import mimo_client

    monkeypatch.setenv("MILOCO_LIFE_MIMO_VISION_MODEL", "mimo-v2.5")
    monkeypatch.setenv("MILOCO_LIFE_MIMO_ASR_MODEL", "mimo-v2.5-asr")

    assert (
        mimo_client.resolve_life_mimo_model(
            configured_model="mimo-v2-omni",
            task="vision",
        )
        == "mimo-v2.5"
    )
    assert (
        mimo_client.resolve_life_mimo_model(
            configured_model="mimo-v2-omni",
            task="asr",
        )
        == "mimo-v2.5-asr"
    )


def test_life_mimo_base_url_keeps_configured_token_plan_host(monkeypatch):
    from miloco.life import mimo_client

    monkeypatch.delenv("MILOCO_LIFE_MIMO_BASE_URL", raising=False)

    assert (
        mimo_client.resolve_life_mimo_base_url(
            configured_base_url="https://token-plan-cn.xiaomimimo.com/v1"
        )
        == "https://token-plan-cn.xiaomimimo.com/v1"
    )


def test_life_mimo_base_url_defaults_to_token_plan_when_config_empty(monkeypatch):
    from miloco.life import mimo_client

    monkeypatch.delenv("MILOCO_LIFE_MIMO_BASE_URL", raising=False)

    assert (
        mimo_client.resolve_life_mimo_base_url(configured_base_url="")
        == "https://token-plan-cn.xiaomimimo.com/v1"
    )


def test_life_mimo_base_url_env_override(monkeypatch):
    from miloco.life import mimo_client

    monkeypatch.setenv("MILOCO_LIFE_MIMO_BASE_URL", "https://example.test/v1")

    assert (
        mimo_client.resolve_life_mimo_base_url(
            configured_base_url="https://token-plan-cn.xiaomimimo.com/v1"
        )
        == "https://example.test/v1"
    )


def test_life_mimo_request_scoped_overrides_win_over_env(monkeypatch):
    from miloco.life import mimo_client

    monkeypatch.setenv("MILOCO_LIFE_MIMO_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("MILOCO_LIFE_MIMO_VISION_MODEL", "env-vision")
    monkeypatch.setenv("MILOCO_LIFE_MIMO_ASR_MODEL", "env-asr")

    with mimo_client.life_mimo_overrides(
        base_url="https://request.example/v1",
        vision_model="request-vision",
        asr_model="request-asr",
    ):
        assert (
            mimo_client.resolve_life_mimo_base_url(
                configured_base_url="https://token-plan-cn.xiaomimimo.com/v1"
            )
            == "https://request.example/v1"
        )
        assert (
            mimo_client.resolve_life_mimo_model(
                configured_model="mimo-v2-omni",
                task="vision",
            )
            == "request-vision"
        )
        assert (
            mimo_client.resolve_life_mimo_model(
                configured_model="mimo-v2-omni",
                task="asr",
            )
            == "request-asr"
        )
