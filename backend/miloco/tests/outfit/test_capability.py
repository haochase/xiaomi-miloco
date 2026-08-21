# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Low-sensitivity in-memory capability contracts for the Outfit plugin."""

from __future__ import annotations

import pytest
from miloco.outfit.capability import (
    OutfitCapabilitySnapshot,
    OutfitCapabilityState,
    OutfitProviderStatus,
)
from pydantic import ValidationError


def _state() -> OutfitCapabilityState:
    return OutfitCapabilityState(
        enabled=True,
        primary_person_configured=True,
        storage_ready=True,
        voice_ingress_configured=False,
        camera_allowlisted=True,
        last_provider_status=OutfitProviderStatus.NEVER_CALLED,
    )


def test_snapshot_is_frozen_exact_and_low_sensitivity() -> None:
    state = _state()

    snapshot = state.snapshot()

    assert tuple(OutfitCapabilitySnapshot.model_fields) == (
        "enabled",
        "primary_person_configured",
        "storage_ready",
        "voice_ingress_configured",
        "camera_allowlisted",
        "last_provider_status",
    )
    assert snapshot.model_dump(mode="json") == {
        "enabled": True,
        "primary_person_configured": True,
        "storage_ready": True,
        "voice_ingress_configured": False,
        "camera_allowlisted": True,
        "last_provider_status": "never_called",
    }
    assert not hasattr(state, "__dict__")
    assert not any(
        sensitive in snapshot.model_dump_json().lower()
        for sensitive in (
            "owner",
            "person_id",
            "path",
            "token",
            "device",
            "model",
            "error_detail",
        )
    )

    with pytest.raises(ValidationError):
        snapshot.enabled = False
    with pytest.raises(ValidationError):
        OutfitCapabilitySnapshot(
            **snapshot.model_dump(),
            owner_person_id="request-selected-owner",
        )


def test_provider_status_is_finite_and_state_updates_require_enum_members() -> None:
    assert tuple(status.value for status in OutfitProviderStatus) == (
        "never_called",
        "last_success",
        "last_error",
        "budget_blocked",
        "not_configured",
    )
    state = _state()

    for status in OutfitProviderStatus:
        state.set_last_provider_status(status)
        assert state.snapshot().last_provider_status is status

    with pytest.raises(TypeError, match="OutfitProviderStatus"):
        state.set_last_provider_status("last_success")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="OutfitProviderStatus"):
        OutfitCapabilityState(
            enabled=True,
            primary_person_configured=True,
            storage_ready=True,
            voice_ingress_configured=False,
            camera_allowlisted=False,
            last_provider_status="never_called",  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        OutfitCapabilitySnapshot(
            enabled=True,
            primary_person_configured=True,
            storage_ready=True,
            voice_ingress_configured=False,
            camera_allowlisted=False,
            last_provider_status="provider-secret-error",
        )
