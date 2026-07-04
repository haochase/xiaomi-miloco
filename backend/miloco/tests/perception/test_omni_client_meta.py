import pytest
from miloco.perception.engine.config import OmniConfig
from miloco.perception.engine.omni import omni_client
from miloco.perception.engine.omni.omni_client import (
    OmniCallMeta,
    build_mimo_chat_body,
    build_mimo_chat_headers,
    call_omni,
    extract_usage,
    normalize_mimo_chat_model,
)


def test_omni_call_meta_dataclass_fields():
    meta = OmniCallMeta(
        latency_ms=100.0,
        retry_count=2,
        input_tokens=500,
        output_tokens=200,
        cached_tokens=100,
        audio_tokens=50,
        video_tokens=50,
        error_code=None,
    )
    assert meta.latency_ms == 100.0
    assert meta.retry_count == 2
    assert meta.input_tokens == 500
    assert meta.error_code is None


def test_omni_call_meta_defaults_minimal():
    meta = OmniCallMeta(latency_ms=50.0)
    assert meta.retry_count == 0
    assert meta.input_tokens is None
    assert meta.error_code is None


def test_from_raw_response_extracts_usage():
    raw = {
        "usage": {
            "prompt_tokens": 1234,
            "completion_tokens": 256,
            "prompt_tokens_details": {
                "cached_tokens": 100,
                "audio_tokens": 0,
                "video_tokens": 50,
            },
        }
    }
    meta = OmniCallMeta.from_raw(raw, latency_ms=80.0, retry_count=1)
    assert meta.latency_ms == 80.0
    assert meta.retry_count == 1
    assert meta.input_tokens == 1234
    assert meta.output_tokens == 256
    assert meta.cached_tokens == 100
    assert meta.video_tokens == 50


def test_from_raw_handles_missing_usage():
    meta = OmniCallMeta.from_raw({}, latency_ms=10.0)
    assert meta.input_tokens is None
    assert meta.output_tokens is None


def test_extract_usage_still_works():
    raw = {"usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    u = extract_usage(raw)
    assert u["input_tokens"] == 100
    assert u["output_tokens"] == 20


def test_token_plan_normalizes_legacy_mimo_models():
    assert (
        normalize_mimo_chat_model(
            "mimo-v2-omni", "https://token-plan-cn.xiaomimimo.com/v1"
        )
        == "mimo-v2.5"
    )
    assert (
        normalize_mimo_chat_model(
            "xiaomi/mimo-v2.5", "https://token-plan-cn.xiaomimimo.com/v1"
        )
        == "mimo-v2.5"
    )
    assert (
        normalize_mimo_chat_model("other-model", "https://example.test/v1")
        == "other-model"
    )


def test_token_plan_shared_helpers_are_safe_for_fused_omni():
    config = OmniConfig(
        model="xiaomi/mimo-v2-omni",
        api_key="test-key",
        base_url="https://token-plan-cn.xiaomimimo.com/v1",
        max_completion_tokens=456,
    )
    messages = [{"role": "user", "content": [{"type": "text", "text": "hi"}]}]

    headers = build_mimo_chat_headers(api_key="test-key", base_url=config.base_url)
    body = build_mimo_chat_body(
        model=config.model,
        messages=messages,
        config=config,
        stream=False,
    )

    assert headers["api-key"] == "test-key"
    assert "Authorization" not in headers
    assert body["model"] == "mimo-v2.5"
    assert body["max_completion_tokens"] == 456
    assert "max_tokens" not in body
    assert body["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_call_omni_token_plan_uses_v25_request_shape(monkeypatch):
    captured = {}

    class _Response:
        status_code = 200
        text = "{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = json
            return _Response()

    monkeypatch.setattr(omni_client.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(omni_client, "fire_record", lambda *args, **kwargs: None)

    await call_omni(
        {
            "system_prompt": "system",
            "user_content": "describe",
            "video_base64": "VIDEO",
            "video_fps": 3,
        },
        OmniConfig(
            model="mimo-v2-omni",
            api_key="test-key",
            base_url="https://token-plan-cn.xiaomimimo.com/v1",
            max_completion_tokens=123,
            temperature=0.0,
            top_p=1.0,
        ),
    )

    assert captured["url"] == "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
    assert captured["headers"]["api-key"] == "test-key"
    assert "Authorization" not in captured["headers"]
    body = captured["body"]
    assert body["model"] == "mimo-v2.5"
    assert body["max_completion_tokens"] == 123
    assert "max_tokens" not in body
    assert body["thinking"] == {"type": "disabled"}
    user_content = body["messages"][1]["content"]
    assert user_content[0]["type"] == "video_url"
    assert user_content[0]["fps"] == 2
    assert user_content[0]["media_resolution"] == "default"
    assert user_content[1] == {"type": "text", "text": "describe"}
