# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Privacy regression for request-validation failures."""

import json
import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from miloco.middleware.exception_handler import handle_exception


class _SentinelSystemError(RuntimeError):
    pass


def test_request_validation_response_and_log_exclude_raw_input_and_context(
    caplog,
) -> None:
    asr_text = "SENTINEL_ASR_customer_meeting"
    owner_id = "SENTINEL_OWNER_primary_person"
    source_device_id = "SENTINEL_DEVICE_living_room_speaker"
    media_path = "E:/private/SENTINEL_PATH/voice.wav"
    dynamic_key = "SENTINEL_DYNAMIC_KEY_source_device_id"
    custom_message = "SENTINEL_CUSTOM_MSG owner token path"
    exc = RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", dynamic_key),
                "msg": custom_message,
                "input": {
                    "text": asr_text,
                    "source_device_id": source_device_id,
                },
                "ctx": {"owner_person_id": owner_id, "path": media_path},
            }
        ]
    )
    request = Request({"type": "http", "method": "POST", "path": "/voice"})

    with caplog.at_level(
        logging.WARNING,
        logger="miloco.middleware.exception_handler",
    ):
        response = handle_exception(request, exc)

    payload = json.loads(response.body)
    assert payload["data"] == [
        {
            "type": "value_error",
            "loc": ["body", "field"],
            "msg": "Invalid value",
        }
    ]
    rendered = response.body.decode("utf-8") + caplog.text
    for sentinel in (
        asr_text,
        owner_id,
        source_device_id,
        media_path,
        dynamic_key,
        custom_message,
    ):
        assert sentinel not in rendered


def test_request_validation_unknown_type_and_extra_key_are_generic(caplog) -> None:
    dynamic_type = "SENTINEL_DYNAMIC_VALIDATION_TYPE"
    extra_key = "SENTINEL_EXTRA_KEY_private_token"
    custom_message = "SENTINEL_UNKNOWN_MSG with secret"
    exc = RequestValidationError(
        [
            {
                "type": dynamic_type,
                "loc": ("body", extra_key),
                "msg": custom_message,
                "input": "SENTINEL_UNKNOWN_INPUT",
                "ctx": {"secret": "SENTINEL_UNKNOWN_CTX"},
            }
        ]
    )
    request = Request({"type": "http", "method": "POST", "path": "/voice"})

    with caplog.at_level(
        logging.WARNING,
        logger="miloco.middleware.exception_handler",
    ):
        response = handle_exception(request, exc)

    assert json.loads(response.body)["data"] == [
        {
            "type": "validation_error",
            "loc": ["body", "field"],
            "msg": "Invalid value",
        }
    ]
    rendered = response.body.decode("utf-8") + caplog.text
    for sentinel in (
        dynamic_type,
        extra_key,
        custom_message,
        "SENTINEL_UNKNOWN_INPUT",
        "SENTINEL_UNKNOWN_CTX",
    ):
        assert sentinel not in rendered


def test_unhandled_exception_response_and_log_exclude_exception_details(
    caplog,
) -> None:
    token = "SENTINEL_TOKEN_provider-secret"
    private_path = "E:/private/SENTINEL_SYSTEM_PATH/provider.json"
    exc = _SentinelSystemError(
        f"provider failed with token={token} at path={private_path}"
    )
    request = Request({"type": "http", "method": "POST", "path": "/voice"})

    with caplog.at_level(
        logging.ERROR,
        logger="miloco.middleware.exception_handler",
    ):
        response = handle_exception(request, exc)

    assert response.status_code == 500
    assert json.loads(response.body) == {
        "code": 9000,
        "message": "Internal server error",
        "data": None,
    }
    response_text = response.body.decode("utf-8")
    assert type(exc).__name__ not in response_text
    assert caplog.messages == ["Unhandled system error - _SentinelSystemError"]
    assert all(record.exc_info is None for record in caplog.records)
    rendered = response_text + caplog.text
    for sentinel in (str(exc), token, private_path):
        assert sentinel not in rendered
