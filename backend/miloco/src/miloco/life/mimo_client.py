# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Life Agent scoped MiMo client for on-demand ASR and visual extraction."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal
from urllib.parse import urlparse

import httpx

from miloco.config import get_settings
from miloco.database.token_usage_repo import fire_record
from miloco.perception.engine.omni.omni_client import (
    OmniError,
    build_mimo_chat_headers,
    resolve_omni_api_key,
)

LifeMimoTask = Literal["asr", "audio", "vision"]

_DEFAULT_ASR_MODEL = "mimo-v2.5-asr"
_DEFAULT_VISION_MODEL = "mimo-v2.5"
_DEFAULT_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
_OVERRIDES: ContextVar[dict[str, str] | None] = ContextVar(
    "life_mimo_overrides", default=None
)


@contextmanager
def life_mimo_overrides(
    *,
    base_url: str | None = None,
    vision_model: str | None = None,
    asr_model: str | None = None,
):
    """Apply request-scoped Life MiMo overrides for one async call chain."""
    overrides = {
        key: value.strip()
        for key, value in {
            "base_url": base_url,
            "vision_model": vision_model,
            "asr_model": asr_model,
        }.items()
        if value and value.strip()
    }
    token = _OVERRIDES.set(overrides or None)
    try:
        yield
    finally:
        _OVERRIDES.reset(token)


def resolve_life_mimo_model(
    *,
    configured_model: str,
    task: LifeMimoTask,
) -> str:
    """Resolve a Life Agent model without changing the global Miloco config."""
    env_name = (
        "MILOCO_LIFE_MIMO_ASR_MODEL"
        if task == "asr"
        else "MILOCO_LIFE_MIMO_VISION_MODEL"
    )
    override = _OVERRIDES.get() or {}
    override_model = override.get("asr_model" if task == "asr" else "vision_model")
    if override_model:
        return override_model
    env_model = os.getenv(env_name)
    if env_model:
        return env_model.strip()
    normalized = configured_model.strip()
    if task == "asr":
        return _DEFAULT_ASR_MODEL
    if normalized in {"mimo-v2-omni", "xiaomi/mimo-v2-omni"}:
        return _DEFAULT_VISION_MODEL
    if normalized.startswith("mimo-v2") or normalized.startswith("xiaomi/mimo-v2"):
        return _DEFAULT_VISION_MODEL
    return normalized or _DEFAULT_VISION_MODEL


def resolve_life_mimo_base_url(*, configured_base_url: str) -> str:
    """Resolve the Life Agent MiMo base URL without mutating global settings."""
    override = _OVERRIDES.get() or {}
    override_base_url = override.get("base_url")
    if override_base_url:
        return override_base_url.rstrip("/")
    env_base_url = os.getenv("MILOCO_LIFE_MIMO_BASE_URL")
    if env_base_url:
        return env_base_url.strip().rstrip("/")
    normalized = configured_base_url.strip().rstrip("/")
    return normalized or _DEFAULT_BASE_URL


async def call_life_mimo_chat(
    *,
    system_prompt: str,
    user_content: str,
    task: LifeMimoTask,
    audio_base64: str | None = None,
    audio_mime_type: str = "audio/m4a",
    image_base64: str | None = None,
    image_mime_type: str = "image/jpeg",
    video_base64: str | None = None,
    video_fps: int = 2,
    video_mime_type: str = "video/mp4",
    max_completion_tokens: int = 512,
    temperature: float = 0.0,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Call MiMo for a Life Agent on-demand task using V2.5-compatible fields."""
    settings = get_settings()
    omni = settings.model.omni
    model = resolve_life_mimo_model(configured_model=omni.model, task=task)
    base_url = resolve_life_mimo_base_url(configured_base_url=omni.base_url)
    api_key = resolve_omni_api_key(omni.api_key)
    if not api_key:
        raise ValueError(
            "MILOCO_MODEL__OMNI__API_KEY is not set. Provide it via config or "
            "environment variable."
        )
    messages = (
        _build_life_asr_messages(audio_base64=audio_base64)
        if task == "asr" and audio_base64
        else _build_life_messages(
            system_prompt=system_prompt,
            user_content=user_content,
            audio_base64=audio_base64,
            audio_mime_type=audio_mime_type,
            image_base64=image_base64,
            image_mime_type=image_mime_type,
            video_base64=video_base64,
            video_fps=video_fps,
            video_mime_type=video_mime_type,
        )
    )
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens,
        "temperature": temperature,
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    if task == "asr":
        body["asr_options"] = {"language": "auto"}
    started_at = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                headers=build_mimo_chat_headers(api_key=api_key, base_url=base_url),
                json=body,
            )
            response.raise_for_status()
            raw = response.json()
            fire_record(model, raw.get("usage", {}), "on_demand")
            return raw
    except httpx.HTTPStatusError as exc:
        raise OmniError(
            _format_life_mimo_http_error(
                exc,
                task=task,
                model=model,
                base_url=base_url,
                api_key=api_key,
                request_body=body,
            ),
            original=exc,
            partial_timing={
                "life_mimo_latency_ms": int((time.monotonic() - started_at) * 1000)
            },
        ) from exc
    except OmniError:
        raise
    except Exception as exc:
        raise OmniError(
            f"call_life_mimo_chat failed: {exc.__class__.__name__}: {exc}",
            original=exc,
            partial_timing={
                "life_mimo_latency_ms": int((time.monotonic() - started_at) * 1000)
            },
        ) from exc


def _build_life_messages(
    *,
    system_prompt: str,
    user_content: str,
    audio_base64: str | None,
    audio_mime_type: str,
    image_base64: str | None,
    image_mime_type: str,
    video_base64: str | None,
    video_fps: int,
    video_mime_type: str,
) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if video_base64:
        content.append(
            {
                "type": "video_url",
                "video_url": {
                    "url": f"data:{_clean_mime_type(video_mime_type)};base64,"
                    f"{video_base64}"
                },
                "fps": video_fps,
                "media_resolution": "default",
            }
        )
    elif image_base64:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{_clean_mime_type(image_mime_type)};base64,"
                    f"{image_base64}"
                },
            }
        )
    elif audio_base64:
        content.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": f"data:{_clean_mime_type(audio_mime_type)};base64,"
                    f"{audio_base64}",
                },
            }
        )
    content.append({"type": "text", "text": user_content})
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content},
    ]


def _build_life_asr_messages(*, audio_base64: str | None) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = []
    if audio_base64:
        content.append(
            {
                "type": "input_audio",
                "input_audio": {
                    "data": f"data:audio/wav;base64,{audio_base64}",
                },
            }
        )
    return [{"role": "user", "content": content}]


def _clean_mime_type(value: str) -> str:
    normalized = value.strip().lower()
    return normalized or "application/octet-stream"


def _format_life_mimo_http_error(
    exc: httpx.HTTPStatusError,
    *,
    task: LifeMimoTask,
    model: str,
    base_url: str,
    api_key: str,
    request_body: dict[str, Any],
) -> str:
    response = exc.response
    request_url = response.request.url if response.request else None
    path = urlparse(str(request_url)).path if request_url else "/chat/completions"
    excerpt = _redact_sensitive_text(response.text[:500], api_key=api_key)
    return (
        "call_life_mimo_chat failed: "
        f"HTTP {response.status_code}; task={task}; model={model}; "
        f"base_url={base_url}; path={path}; "
        f"request_shape={_summarize_life_mimo_request_shape(request_body)}; "
        f"response_excerpt={excerpt}"
    )


def _redact_sensitive_text(value: str, *, api_key: str) -> str:
    text = value.replace("\r", " ").replace("\n", " ").strip()
    if api_key:
        text = text.replace(api_key, "[redacted]")
    return text


def _summarize_life_mimo_request_shape(body: dict[str, Any]) -> str:
    messages = body.get("messages")
    message_items = messages if isinstance(messages, list) else []
    roles: list[str] = []
    modalities: list[str] = []
    for message in message_items:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if isinstance(role, str) and role:
            roles.append(role)
        content = message.get("content")
        if isinstance(content, str):
            modalities.append("text")
        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if isinstance(item_type, str) and item_type:
                    modalities.append(item_type)
    thinking = body.get("thinking")
    thinking_type = (
        thinking.get("type")
        if isinstance(thinking, dict) and isinstance(thinking.get("type"), str)
        else "unset"
    )
    return "; ".join(
        [
            f"message_roles={_join_unique(roles)}",
            f"modalities={_join_unique(modalities)}",
            f"max_completion_tokens={body.get('max_completion_tokens')}",
            f"thinking={thinking_type}",
            f"stream={body.get('stream')}",
            f"asr_options={'present' if 'asr_options' in body else 'absent'}",
        ]
    )


def _join_unique(values: list[str]) -> str:
    seen: list[str] = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return ",".join(seen) if seen else "none"
