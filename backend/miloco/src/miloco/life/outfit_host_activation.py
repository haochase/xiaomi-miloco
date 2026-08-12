# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Settings-to-host adapter for the optional local Outfit integration."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from fastapi import FastAPI

from miloco.life.outfit_host_composition import install_outfit_host_composition
from miloco.life.outfit_installation import OutfitInstallConfig, OutfitInstallResult


class OutfitHostSettings(Protocol):
    """Only the host settings needed by the Outfit installation boundary."""

    features: object
    directories: object


def install_outfit_from_settings(
    app: FastAPI,
    *,
    settings: OutfitHostSettings,
    clock_ms: Callable[[], int] | None = None,
) -> OutfitInstallResult:
    """Install the optional Outfit surface from explicit host configuration."""
    outfit = settings.features.outfit
    return install_outfit_host_composition(
        app,
        config=OutfitInstallConfig(
            enabled=outfit.enabled,
            primary_person_id=outfit.primary_person_id,
            workspace_dir=settings.directories.workspace_dir,
        ),
        clock_ms=clock_ms or _clock_ms,
    )


def _clock_ms() -> int:
    return int(time.time() * 1_000)
