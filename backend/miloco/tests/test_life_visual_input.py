# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Visual input compatibility tests for life-domain live demos."""

from __future__ import annotations

import base64

import pytest
from miloco.life.visual_input import (
    VisualObservation,
    VisualObservationError,
    observation_from_live_request,
)
from pydantic import ValidationError


def test_observation_from_legacy_clip_request_keeps_short_clip_metadata():
    clip_base64 = base64.b64encode(b"fake mp4 bytes").decode("ascii")

    observation = observation_from_live_request(
        source_id="live_camera_1182348802_123",
        prompt="focus on pantry items",
        clip_base64=clip_base64,
        mimo_payload=None,
    )

    assert observation.source_id == "live_camera_1182348802_123"
    assert observation.source_type == "short_clip"
    assert observation.media_format == "mp4"
    assert observation.content_base64 == clip_base64
    assert observation.prompt == "focus on pantry items"
    assert observation.sampling.duration_seconds is None
    assert observation.sampling.frame_index is None


def test_observation_accepts_future_snapshot_metadata_without_media_dependency():
    observation = VisualObservation(
        source_id="snapshot_001",
        source_type="snapshot",
        media_format="jpeg",
        content_base64=base64.b64encode(b"fake jpeg bytes").decode("ascii"),
        prompt="look for a white shirt",
    )

    assert observation.source_type == "snapshot"
    assert observation.media_format == "jpeg"
    assert observation.prompt == "look for a white shirt"


def test_observation_accepts_future_sampled_frame_metadata():
    observation = VisualObservation(
        source_id="frame_001",
        source_type="sampled_frame",
        media_format="jpeg",
        content_base64=base64.b64encode(b"fake frame bytes").decode("ascii"),
        sampling={"fps": 1.0, "frame_index": 12},
    )

    assert observation.source_type == "sampled_frame"
    assert observation.sampling.fps == 1.0
    assert observation.sampling.frame_index == 12


def test_manual_payload_observation_requires_payload_not_media():
    observation = observation_from_live_request(
        source_id="provided_payload_probe",
        prompt="ignored for provided payload",
        clip_base64=None,
        mimo_payload={"source_id": "provided_payload_probe", "wardrobe": []},
    )

    assert observation.source_type == "manual_payload"
    assert observation.content_base64 is None
    assert observation.mimo_payload == {
        "source_id": "provided_payload_probe",
        "wardrobe": [],
    }


def test_observation_rejects_blank_or_invalid_media_payloads():
    with pytest.raises(VisualObservationError):
        observation_from_live_request(
            source_id="live_camera_1182348802_123",
            prompt="focus on pantry items",
            clip_base64="not-base64",
            mimo_payload=None,
        )

    with pytest.raises(ValidationError):
        VisualObservation(
            source_id="stream_001",
            source_type="stream",
            media_format="mp4",
            content_base64=base64.b64encode(b"stream metadata only").decode("ascii"),
        )
