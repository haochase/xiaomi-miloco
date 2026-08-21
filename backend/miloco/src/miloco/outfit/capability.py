# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Low-sensitivity in-memory capability state for the Outfit plugin."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class OutfitProviderStatus(str, Enum):
    """Finite low-sensitivity outcomes for the most recent provider attempt."""

    NEVER_CALLED = "never_called"
    LAST_SUCCESS = "last_success"
    LAST_ERROR = "last_error"
    BUDGET_BLOCKED = "budget_blocked"
    NOT_CONFIGURED = "not_configured"


class OutfitCapabilitySnapshot(BaseModel):
    """Immutable public capability data without operational identifiers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool
    primary_person_configured: bool
    storage_ready: bool
    voice_ingress_configured: bool
    camera_allowlisted: bool
    last_provider_status: OutfitProviderStatus


class OutfitCapabilityState:
    """Hold capability flags in memory and return detached immutable snapshots."""

    __slots__ = (
        "_enabled",
        "_primary_person_configured",
        "_storage_ready",
        "_voice_ingress_configured",
        "_camera_allowlisted",
        "_last_provider_status",
    )

    def __init__(
        self,
        *,
        enabled: bool,
        primary_person_configured: bool,
        storage_ready: bool,
        voice_ingress_configured: bool,
        camera_allowlisted: bool,
        last_provider_status: OutfitProviderStatus,
    ) -> None:
        self._enabled = enabled
        self._primary_person_configured = primary_person_configured
        self._storage_ready = storage_ready
        self._voice_ingress_configured = voice_ingress_configured
        self._camera_allowlisted = camera_allowlisted
        self._last_provider_status = _require_provider_status(last_provider_status)

    def snapshot(self) -> OutfitCapabilitySnapshot:
        """Return the current six-field state without consulting external systems."""

        return OutfitCapabilitySnapshot(
            enabled=self._enabled,
            primary_person_configured=self._primary_person_configured,
            storage_ready=self._storage_ready,
            voice_ingress_configured=self._voice_ingress_configured,
            camera_allowlisted=self._camera_allowlisted,
            last_provider_status=self._last_provider_status,
        )

    def set_last_provider_status(self, status: OutfitProviderStatus) -> None:
        """Record only a member of the finite public provider-status enum."""

        self._last_provider_status = _require_provider_status(status)


def _require_provider_status(status: OutfitProviderStatus) -> OutfitProviderStatus:
    if not isinstance(status, OutfitProviderStatus):
        raise TypeError("status must be an OutfitProviderStatus")
    return status
