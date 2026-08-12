# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Controlled host-installation boundary for the optional Outfit plugin.

This module intentionally does not import the Outfit routers. The eventual
composition root supplies a lazy installer only after it has built the
authenticated, owner-bound HTTP adapters.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import FastAPI

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutfitInstallConfig:
    """Configuration required before the host may load the optional plugin."""

    enabled: bool = False
    primary_person_id: str | None = None
    workspace_dir: Path | str | None = None


@dataclass(frozen=True)
class OutfitRuntimeContext:
    """Resolved non-secret runtime values passed to the plugin composition."""

    primary_person_id: str
    workspace_dir: Path
    storage_dir: Path


@dataclass(frozen=True)
class OutfitInstallResult:
    """Safe installation result suitable for later capability publication."""

    installed: bool
    reason: Literal[
        "disabled",
        "invalid_configuration",
        "install_failed",
        "installed",
        "configuration_conflict",
    ]


OutfitPluginInstaller = Callable[[FastAPI, OutfitRuntimeContext], None]

_INSTALLATION_STATE = "outfit_plugin_installation"


def install_outfit_plugin_if_enabled(
    app: FastAPI,
    *,
    config: OutfitInstallConfig,
    installer: OutfitPluginInstaller,
) -> OutfitInstallResult:
    """Install once only after an explicit, valid local configuration.

    A disabled or invalid configuration never invokes ``installer``. A failed
    installer is not persisted, so a later explicit restart can retry it.
    """
    if not config.enabled:
        return OutfitInstallResult(installed=False, reason="disabled")

    runtime = _resolve_runtime_context(config)
    if runtime is None:
        logger.warning("Outfit plugin installation skipped: invalid configuration")
        return OutfitInstallResult(installed=False, reason="invalid_configuration")

    existing = getattr(app.state, _INSTALLATION_STATE, None)
    if existing is not None:
        if existing.runtime == runtime:
            return OutfitInstallResult(installed=True, reason="installed")
        logger.warning("Outfit plugin installation skipped: configuration conflict")
        return OutfitInstallResult(installed=False, reason="configuration_conflict")

    try:
        installer(app, runtime)
    except Exception:  # noqa: BLE001 - optional plugin must not stop the host.
        logger.warning("Outfit plugin installation failed")
        return OutfitInstallResult(installed=False, reason="install_failed")

    setattr(app.state, _INSTALLATION_STATE, _InstalledOutfitPlugin(runtime=runtime))
    return OutfitInstallResult(installed=True, reason="installed")


def is_outfit_plugin_installed(app: FastAPI) -> bool:
    """Return whether the optional plugin completed installation in this host."""
    return isinstance(
        getattr(app.state, _INSTALLATION_STATE, None),
        _InstalledOutfitPlugin,
    )


@dataclass(frozen=True)
class _InstalledOutfitPlugin:
    runtime: OutfitRuntimeContext


def _resolve_runtime_context(
    config: OutfitInstallConfig,
) -> OutfitRuntimeContext | None:
    """Reject ambiguous owner and CWD-dependent storage before any plugin import."""
    owner = (config.primary_person_id or "").strip()
    if not owner or config.workspace_dir is None:
        return None

    workspace_dir = Path(config.workspace_dir)
    if not workspace_dir.is_absolute():
        return None

    return OutfitRuntimeContext(
        primary_person_id=owner,
        workspace_dir=workspace_dir,
        storage_dir=workspace_dir / "outfit",
    )
